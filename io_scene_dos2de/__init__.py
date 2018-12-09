# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# ##### END GPL LICENSE BLOCK #####

import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty

from bpy_extras.io_utils import (
    ExportHelper,
    axis_conversion,
    orientation_helper_factory
)

from math import radians
from mathutils import Euler, Matrix

bl_info = {
    "name": "DOS2DE Collada Exporter",
    "author": "LaughingLeader",
    "blender": (2, 7, 9),
    "api": 38691,
    "location": "File > Import-Export",
    "description": ("Export DAE Scenes."),
    "warning": "",
    "wiki_url": (""),
    "tracker_url": "",
    "support": "TESTING",
    "category": "Import-Export"}

if "bpy" in locals():
    import imp
    if "export_dae" in locals():
        imp.reload(export_dae) # noqa

class ExportDAE(bpy.types.Operator, ExportHelper):
    """Selection to DAE"""
    bl_idname = "export_dos2scene.dae"
    bl_label = "Export DAE"
    bl_options = {"PRESET", "REGISTER", "UNDO"}

    filename_ext = ".dae"
    filter_glob = StringProperty(default="*.dae", options={"HIDDEN"})
    
    def update_filepath(self, context):
        if self.filepath != "" and self.last_filepath == "":
            self.last_filepath = self.filepath
        
        if self.filepath != "":
            if self.auto_name == "LAYER":
                for i in range(20):
                    if (bpy.data.scenes["Scene"].layers[i]):
                        self.auto_filepath = self.filepath.replace(
                                bpy.path.display_name_from_filepath(self.filepath), 
                                bpy.data.scenes["Scene"].namedlayers.layers[i].name)
                        self.update_path = True
            elif self.auto_name == "ACTION":
                armature = None
                if self.use_active_layers:
                    for i in range(20):
                        if context.scene.layers[i]:
                            for obj in context.scene.objects:
                                if obj.layers[i] and obj.type == "ARMATURE":
                                    armature = obj
                                    break
                elif self.use_export_selected:
                    for obj in context.scene.objects:
                        if obj.select and obj.type == "ARMATURE":
                            armature = obj
                            break
                else:
                    for obj in context.scene.objects:
                        if obj.type == "ARMATURE":
                            armature = obj
                            break
                if armature is not None:
                    anim_name = (armature.animation_data.action.name
                            if armature.animation_data is not None and
                            armature.animation_data.action is not None
                            else "")
                    if anim_name != "":
                        self.auto_filepath = self.filepath.replace(
                                bpy.path.display_name_from_filepath(self.filepath), 
                                anim_name)
                        self.update_path = True
            elif self.auto_name == "DISABLED" and self.last_filepath != "":
                self.auto_filepath = self.last_filepath
                self.update_path = True
            if self.update_path:
                print("[DOS2DE] Filepath set to " + str(self.auto_filepath))
        return

    # List of operator properties, the attributes will be assigned
    # to the class instance from the operator settings before calling
    object_types = EnumProperty(
        name="Object Types",
        options={"ENUM_FLAG"},
        items=(("EMPTY", "Empty", ""),
               ("CAMERA", "Camera", ""),
               ("LAMP", "Lamp", ""),
               ("ARMATURE", "Armature", ""),
               ("MESH", "Mesh", ""),
               ("CURVE", "Curve", ""),
               ),
        default={"EMPTY", "CAMERA", "LAMP", "ARMATURE", "MESH", "CURVE"},
        )

    use_export_selected = BoolProperty(
        name="Selected Objects",
        description="Export only selected objects (and visible in active "
                    "layers if that applies).",
        default=False,
        )
    yup_enabled = EnumProperty(
        name="Y-Up",
        description="Converts from Z-up to Y-up.",
        items=(("DISABLED", "Disabled", ""),
               ("ROTATE", "Rotate", "Rotate the object towards y-up"),
               ("ACTION", "Flag", "Flag the object as being y-up without rotating it")),
        default=("DISABLED")
        )
    xflip_armature = BoolProperty(
        name="X-Flip Armature",
        description="Flips the armature on the x-axis.",
        default=False,
        )
    xflip_mesh = BoolProperty(
        name="X-Flip Mesh",
        description="Flips the mesh on the x-axis.",
        default=False,
        )
    auto_name = EnumProperty(
        name="Name",
        description="Auto-generate a filename based on a property name.",
        items=(("DISABLED", "Disabled", ""),
               ("LAYER", "Layer Name", ""),
               ("ACTION", "Action Name", "")),
        default=("DISABLED"),
        update=update_filepath
        )
    use_mesh_modifiers = BoolProperty(
        name="Apply Modifiers",
        description="Apply modifiers to mesh objects (on a copy!).",
        default=False,
        )
    use_exclude_armature_modifier = BoolProperty(
        name="Exclude Armature Modifier",
        description="Exclude the armature modifier when applying modifiers "
                      "(otherwise animation will be applied on top of the last pose)",
        default=True,
        )
    use_tangent_arrays = BoolProperty(
        name="Tangent Arrays",
        description="Export Tangent and Binormal arrays "
                    "(for normalmapping).",
        default=False,
        )
    use_triangles = BoolProperty(
        name="Triangulate",
        description="Export Triangles instead of Polygons.",
        default=False,
        )

    use_copy_images = BoolProperty(
        name="Copy Images",
        description="Copy Images (create images/ subfolder)",
        default=False,
        )
    use_active_layers = BoolProperty(
        name="Active Layers",
        description="Export only objects on the active layers.",
        default=True,
        )
    use_exclude_ctrl_bones = BoolProperty(
        name="Exclude Control Bones",
        description=("Exclude skeleton bones with names beginning with 'ctrl' "
                     "or bones which are not marked as Deform bones."),
        default=True,
        )
    use_anim = BoolProperty(
        name="Export Animation",
        description="Export keyframe animation",
        default=False,
        )
    use_anim_action_all = BoolProperty(
        name="All Actions",
        description=("Export all actions for the first armature found "
                     "in separate DAE files"),
        default=False,
        )
    use_anim_skip_noexp = BoolProperty(
        name="Skip (-noexp) Actions",
        description="Skip exporting of actions whose name end in (-noexp)."
                    " Useful to skip control animations.",
        default=True,
        )
    use_anim_optimize = BoolProperty(
        name="Optimize Keyframes",
        description="Remove double keyframes",
        default=True,
        )

    use_shape_key_export = BoolProperty(
        name="Shape Keys",
        description="Export shape keys for selected objects.",
        default=False,
        )
        
    anim_optimize_precision = FloatProperty(
        name="Precision",
        description=("Tolerence for comparing double keyframes "
                     "(higher for greater accuracy)"),
        min=1, max=16,
        soft_min=1, soft_max=16,
        default=6.0,
        )

    use_metadata = BoolProperty(
        name="Use Metadata",
        default=True,
        options={"HIDDEN"},
        )

    update_path = BoolProperty(
        default=False,
        options={"HIDDEN"},
        )
        
    auto_filepath = StringProperty(
        name="Auto Filepath",
        default="",
        options={"HIDDEN"},
        )     
        
    last_filepath = StringProperty(
        name="Last Filepath",
        default="",
        options={"HIDDEN"},
        )
        
    @property
    def check_extension(self):
        return True
    
    def check(self, context):
        update = False
        if self.update_path:
            update = True
            self.update_path = False
            if self.filepath != self.auto_filepath:
                self.filepath = bpy.path.ensure_ext(self.auto_filepath, self.filename_ext)
                print("[DOS2DE] Filepath is actually: " + self.filepath)

        return update
        
    def invoke(self, context, event):
        if self.filepath != "" and self.last_filepath == "":
            self.last_filepath = self.filepath
        self.update_filepath(context)
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not self.filepath:
            raise Exception("filepath not set")
        
        current_mode = bpy.context.object.mode
        bpy.ops.object.mode_set(mode="OBJECT")
        
        euler = Euler(map(radians, (-90, 0, 0)), 'XYZ')
        
        if self.xflip_mesh:
            import bmsh
            bm = bmesh.new()
        
        modifyObjects = []
        rotatedObjects = []
        selectedObjects = []
        activeObject = None
        
        if bpy.context.scene.objects.active:
            activeObject = bpy.context.scene.objects.active
        
        for obj in context.scene.objects:
            if obj.select:
                selectedObjects.append(obj)
                if self.use_export_selected:
                    modifyObjects.append(obj)   
        
        if self.use_active_layers:
            for i in range(20):
                if context.scene.layers[i]:
                    for obj in context.scene.objects:
                        if obj.layers[i]:
                            modifyObjects.append(obj)
        elif not self.use_export_selected:
            modifyObjects.extend(context.scene.objects)
        
        for obj in modifyObjects:
            if self.yup_enabled == "ROTATE" and not obj.parent:
                obj.rotation_euler = euler
                rotatedObjects.append(obj)
            if self.xflip_armature and obj.type == "ARMATURE":
                obj.scale = (1.0, -1.0, 1.0)
            if self.xflip_mesh and obj.type == "MESH":
                obj.scale = (1.0, -1.0, 1.0)
                bm.from_mesh(obj)
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                bm.to_mesh(obj)
                bm.clear()
                obj.update()
            obj.select = True

        bpy.ops.object.transform_apply(rotation = True, scale = True)

        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "global_scale",
                                            "check_existing",
                                            "filter_glob",
                                            "xna_validate",
                                            ))

        from . import export_dae
        result = export_dae.save(self, context, **keywords)
        
        euler = Euler(map(radians, (90, 0, 0)), 'XYZ')
        
        for obj in modifyObjects:
            if obj in rotatedObjects:
                obj.rotation_euler = euler
                rotatedObjects.remove(obj)
            if self.xflip_armature and obj.type == "ARMATURE":
                obj.scale = (-1.0, 1.0, 1.0)
            if self.xflip_mesh and obj.type == "MESH":
                obj.scale = (-1.0, 1.0, 1.0)
                bm.from_mesh(obj)
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                bm.to_mesh(obj)
                bm.clear()
                obj.update()
            obj.select = True

        bpy.ops.object.transform_apply(rotation = True, scale = True)
        
        bpy.ops.object.select_all(action='DESELECT')
        
        for obj in selectedObjects:
            obj.select = True
        
        if activeObject is not None:
            bpy.context.scene.objects.active = activeObject
        
        # Return to previous mode
        bpy.ops.object.mode_set ( mode = current_mode )
           
        return result


def menu_func(self, context):
    self.layout.operator(ExportDAE.bl_idname,
                         text="DOS2DE Collada (.dae)")


def register():
    bpy.utils.register_module(__name__)

    bpy.types.INFO_MT_file_export.append(menu_func)


def unregister():
    bpy.utils.unregister_module(__name__)

    bpy.types.INFO_MT_file_export.remove(menu_func)


if __name__ == "__main__":
    register()

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
import bmesh
import os
import os.path
import subprocess

from bpy.types import Operator, AddonPreferences
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty

from bpy_extras.io_utils import ExportHelper

from math import radians
from mathutils import Euler, Matrix

bl_info = {
    "name": "Divinity Collada Exporter",
    "author": "LaughingLeader",
    "blender": (2, 7, 9),
    "api": 38691,
    "location": "File > Import-Export",
    "description": ("Export DAE Scenes."),
    "warning": "",
    "wiki_url": (""),
    "tracker_url": "",
    "support": "COMMUNITY",
    "category": "Import-Export"}

if "bpy" in locals():
    import imp
    if "export_dae" in locals():
        imp.reload(export_dae) # noqa

class ExportColladaAddonPreferences(AddonPreferences):
    bl_idname = __name__

    lslib_path = StringProperty(
        name="Divine Path",
        description="The path to divine.exe, used to convert from dae to gr2.",
        subtype='FILE_PATH',
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Divinity Export Addon Preferences")
        layout.prop(self, "lslib_path")

class GR2_ExtraProperties(bpy.types.PropertyGroup):
    """GR2 Extra Properties"""
    rigid = BoolProperty(
        name="Rigid",
        default=False,
        description="For meshes lacking an armature modifier. Typically used for weapons."
    )
    cloth = BoolProperty(
        name="Cloth",
        default=False,
        description="Meshes with vertex painting will be flagged for cloth physics."
    )
    meshproxy = BoolProperty(
        name="MeshProxy",
        default=False,
        description="Flags the mesh as a meshproxy, used for displaying overlay effects on a weapon, and AllSpark MeshEmiters."
    )

    def draw(self, context, obj):
        obj.prop(self, "rigid")
        obj.prop(self, "cloth")
        obj.prop(self, "meshproxy")

class GR2_ExportSettings(bpy.types.PropertyGroup):
    """GR2 Export Options"""
    extras = bpy.props.PointerProperty(
        type=GR2_ExtraProperties,
        name="Extra Properties"
    )
    yup_conversion = BoolProperty(
        name="Convert to Y-Up",
        default=False
    )
    force_legacy = BoolProperty(
        name="Force Legacy GR2 Version Tag",
        default=False
    )
    store_indices = BoolProperty(
        name="Store Compact Tri Indices",
        default=True
    )
    create_dummyskeleton = BoolProperty(
        name="Create Dummy Skeleton",
        default=True
    )

    def draw(self, context, obj):
        obj.label("GR2 Options")
        obj.prop(self, "yup_conversion")
        obj.prop(self, "force_legacy")
        obj.prop(self, "store_indices")
        obj.prop(self, "create_dummyskeleton")

        obj.label("Extra Properties")
        extrasobj = obj.row(align=False)
        self.extras.draw(context, extrasobj)

class Divine_ExportSettings(bpy.types.PropertyGroup):
    """Divine GR2 Conversion Settings"""
    gr2_settings = bpy.props.PointerProperty(
        type=GR2_ExportSettings,
        name="GR2 Export Options"
    )

    delete_collada = BoolProperty(
        name="Delete Exported Collada File",
        default=True,
        description="The resulting .dae file will be deleted after being converted to gr2"
    )

    xflip_skeletons = BoolProperty(
        name="X-Flip Skeletons",
        default=False
    )
    xflip_meshes = BoolProperty(
        name="X-Flip Meshes",
        default=False
    )

    flip_uvs = BoolProperty(
        name="Flip UVs",
        default=True
    )
    filter_uvs = BoolProperty(
        name="Filter UVs",
        default=False
    )
    export_normals = BoolProperty(
        name="Export Normals",
        default=True
    )
    export_tangents = BoolProperty(
        name="Export Tangent/Bitangent",
        default=True
    )
    export_uvs = BoolProperty(
        name="Export UVs",
        default=True
    )
    export_colors = BoolProperty(
        name="Export Colors",
        default=True
    )
    deduplicate_vertices = BoolProperty(
        name="Deduplicate Vertices",
        default=True
    )
    deduplicate_uvs = BoolProperty(
        name="Deduplicate UVs",
        default=True
    )
    recalculate_normals = BoolProperty(
        name="Recalculate Normals",
        default=False
    )
    recalculate_tangents = BoolProperty(
        name="Recalculate Tangent/Bitangent",
        default=False
    )
    recalculate_iwt = BoolProperty(
        name="Recalculate Inverse World Transforms",
        default=False
    )

    drawable_props = [
            "xflip_skeletons",
            "xflip_meshes",
            "flip_uvs",
            "filter_uvs",
            "export_normals",
            "export_tangents",
            "export_uvs",
            "export_colors",
            "deduplicate_vertices",
            "deduplicate_uvs",
            "recalculate_normals",
            "recalculate_tangents",
            "recalculate_iwt"
            ]

    def draw(self, context, obj):
        obj.label("GR2 Export Settings")
        gr2box = obj.box()
        self.gr2_settings.draw(context, gr2box)

        #col = obj.column(align=True)
        obj.label("Export Options")
        for prop in self.drawable_props:
            obj.prop(self, prop)

class ExportDAE(Operator, ExportHelper):
    """Export to Collada with Divinity-specific options (.dae)"""
    bl_idname = "export_scene.dos2de_collada"
    bl_label = "Export Divinity DAE"
    bl_options = {"PRESET", "REGISTER", "UNDO"}

    filename_ext = StringProperty(
        name="File Extension",
        options={"HIDDEN"},
        default=".dae"
    )

    filter_glob = StringProperty(default="*.dae", options={"HIDDEN"})
    
    filename = StringProperty(
        name="File Name",
        options={"HIDDEN"}
    )
    directory = StringProperty(
        name="Directory",
        options={"HIDDEN"}
    )

    def build_gr2_options(self):
        export_str = ""
        # Possible args:
        #"export-normals;export-tangents;export-uvs;export-colors;deduplicate-vertices;
        # deduplicate-uvs;recalculate-normals;recalculate-tangents;recalculate-iwt;flip-uvs;
        # force-legacy-version;compact-tris;build-dummy-skeleton;apply-basis-transforms;conform"

        divine_args = {
            "export_normals"            : "export-normals",
            "export_tangents"           : "export-tangents",
            "export_uvs"                : "export-uvs",
            "export_colors"             : "export-colors",
            "deduplicate_vertices"      : "deduplicate-vertices",
            "deduplicate_uvs"           : "deduplicate-uvs",
            "recalculate_normals"       : "recalculate-normals",
            "recalculate_tangents"      : "recalculate-tangents",
            "recalculate_iwt"           : "recalculate-iwt",
            "flip_uvs"                  : "flip-uvs"
        }

        gr2_args = {
            "force_legacy"              : "force-legacy-version",
            "store_indices"             : "compact-tris",
            "create_dummyskeleton"      : "build-dummy-skeleton",
            "yup_conversion"            : "apply-basis-transforms"
            #"conform"					: "conform"
        }

        for prop,arg in divine_args.items():
            val = getattr(self.divine_settings, prop)
            if val is True:
                export_str += arg + " "

        gr2_settings = self.divine_settings.gr2_settings

        for prop,arg in gr2_args.items():
            val = getattr(gr2_settings, prop)
            if val is True:
                export_str += arg + " "

        return export_str;

    def apply_preset(self, context):
        if self.use_preset == "NONE":
            return
        elif self.use_preset == "MODEL":
            self.object_types = {"ARMATURE", "MESH"}
            self.yup_enabled = "ROTATE"
            self.use_tangent_arrays = True
            self.use_triangles = True
            self.use_active_layers = True
            self.auto_name = "LAYER"

            self.xflip_armature = False
            self.xflip_mesh = False
            self.use_copy_images = False
            self.use_exclude_ctrl_bones = False
            self.use_anim = False
            self.use_anim_action_all = False
            self.use_anim_skip_noexp = False
            self.use_anim_optimize = False
            self.use_shape_key_export = False

        elif self.use_preset == "ANIMATION":
            self.object_types = {"ARMATURE"}
            self.yup_enabled = "ROTATE"
            self.use_tangent_arrays = False
            self.use_triangles = False
            self.use_active_layers = True
            self.auto_name = "ACTION"

            self.xflip_armature = False
            self.xflip_mesh = False
            self.use_copy_images = False
            self.use_exclude_ctrl_bones = True
            self.use_anim = True
            self.use_anim_action_all = False
            self.use_anim_skip_noexp = True
            self.use_anim_optimize = False
            self.use_shape_key_export = False

        elif self.use_preset == "MESHPROXY":
            self.object_types = {"MESH"}
            self.yup_enabled = "ROTATE"
            self.use_tangent_arrays = True
            self.use_triangles = True
            self.use_active_layers = True
            self.auto_name = "LAYER"

            self.xflip_armature = False
            self.xflip_mesh = False
            self.use_copy_images = False
            self.use_exclude_ctrl_bones = False
            self.use_anim = False
            self.use_anim_action_all = False
            self.use_anim_skip_noexp = False
            self.use_anim_optimize = False
            self.use_shape_key_export = False
        
        self.use_preset = "NONE"

    def update_filepath(self, context):
        if self.directory == "":
            self.directory = os.path.dirname(bpy.data.filepath)

        if self.filepath == "":
            #self.filepath = bpy.path.ensure_ext(str.replace(bpy.path.basename(bpy.data.filepath), ".blend", ""), self.filename_ext)
            self.filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, str.replace(bpy.path.basename(bpy.data.filepath), ".blend", "")), self.filename_ext)

        if self.filepath != "" and self.last_filepath == "":
            self.last_filepath = self.filepath

        if self.filepath != "":
            if self.auto_name == "LAYER":
                for i in range(20):
                    if (bpy.data.scenes["Scene"].layers[i]):
                        self.auto_filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, 
                                                bpy.data.scenes["Scene"].namedlayers.layers[i].name), 
                                            self.filename_ext)
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
                        self.auto_filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, anim_name), self.filename_ext)
                        self.update_path = True
            elif self.auto_name == "DISABLED" and self.last_filepath != "":
                self.auto_filepath = self.last_filepath
                self.update_path = True
            if self.update_path:
                print("[DOS2DE] Filepath set to " + str(self.auto_filepath))
        return

    use_preset = EnumProperty(
        name="Preset",
        description="Use a built-in preset.",
        items=(("NONE", "None", ""),
               ("MESHPROXY", "MeshProxy", "Use default meshproxy settings"),
               ("ANIMATION", "Animation", "Use default animation settings"),
               ("MODEL", "Model", "Use default model settings")),
        default=("NONE"),
        update=apply_preset
        )

    misc_settings_visible = BoolProperty(
        name="Misc Settings",
        default=False,
        options={"HIDDEN"}
    )

    convert_gr2 = BoolProperty(
        name="Convert to GR2",
        default=False
    )

    extra_data_disabled = BoolProperty(
        name="Disable Extra Data",
        default=False
    )

    convert_gr2_options_visible = BoolProperty(
        name="GR2 Options",
        default=False,
        options={"HIDDEN"}
    )

    divine_settings = bpy.props.PointerProperty(
        type=Divine_ExportSettings,
        name="GR2 Settings",
    )

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
        name="Selected Only",
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
        name="Auto-Name",
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
        name="Active Layers Only",
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
        name="Export All Actions",
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
        name="Export Shape Keys",
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
        options={"HIDDEN"}
        )
        
    auto_filepath = StringProperty(
        name="Auto Filepath",
        default="",
        options={"HIDDEN"}
        )     
        
    last_filepath = StringProperty(
        name="Last Filepath",
        default="",
        options={"HIDDEN"}
        )

    #def __init__(self):
    #    props = dir(self)

    #    for prop in props:
    #        if not prop.startswith('__'):
    #            val = getattr(self, prop)
    #            if not callable(val):
    #                if val.options != "HIDDEN":
    #                    proptype = type(getattr(self, prop))
    #                    print(proptype)
    #                    if prop is bpy.types.Property:
    #                        list.append(self.drawable_props, prop)

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "object_types")

        col = layout.column(align=True)
        col.prop(self, "use_preset")

        box = layout.box()
        box.prop(self, "auto_name")
        box.prop(self, "yup_enabled")
       
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "use_active_layers")
        row.prop(self, "use_export_selected")

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "use_tangent_arrays")
        row.prop(self, "use_triangles")

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "use_mesh_modifiers")
        if self.use_mesh_modifiers:
            row.prop(self, "use_exclude_armature_modifier")

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "xflip_armature")
        row.prop(self, "xflip_mesh")

        box = layout.box()
        box.prop(self, "use_anim")
        if self.use_anim:
            box.label("Animation Settings")
            box.prop(self, "use_anim_action_all")
            box.prop(self, "use_anim_skip_noexp")
            box.prop(self, "use_anim_optimize")
            box.prop(self, "anim_optimize_precision")

        box = layout.box()
        box.prop(self, "convert_gr2")

        if self.convert_gr2:
            box.prop(self.divine_settings, "delete_collada")
            label = "Show GR2 Options" if not self.convert_gr2_options_visible else "Hide GR2 Options"
            box.prop(self, "convert_gr2_options_visible", text=label, toggle=True)

            if self.convert_gr2_options_visible:
                self.divine_settings.draw(context, box)

        col = layout.column(align=True)
        label = "Misc Settings" if not self.convert_gr2_options_visible else "Misc Settings"
        col.prop(self, "misc_settings_visible", text=label, toggle=True)
        if self.misc_settings_visible:
            box = layout.box()
            box.prop(self, "use_exclude_ctrl_bones")
            box.prop(self, "use_shape_key_export")
            box.prop(self, "use_copy_images")
            
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
                #print("[DOS2DE] Filepath is actually: " + self.filepath)

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
        
        user_preferences = context.user_preferences
        addon_prefs = user_preferences.addons[__name__].preferences

        current_mode = bpy.context.object.mode
        bpy.ops.object.mode_set(mode="OBJECT")
        
        if self.xflip_mesh:
            bm = bmesh.new()
        
        modifyObjects = []
        rotatedObjects = []
        selectedObjects = []
        originalRotations = {}
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
        
        objFlipped = False
        objRotated = False
        
        for obj in modifyObjects:
            if self.yup_enabled == "ROTATE" and not obj.parent:
                originalRotations[obj.name] = obj.rotation_euler.copy()
                print("Saved rotation " + obj.name + " : " + str(originalRotations[obj.name]))
                obj.rotation_euler = (obj.rotation_euler.to_matrix() * Matrix.Rotation(radians(-90), 3, 'X')).to_euler()
                rotatedObjects.append(obj)
                objRotated = True
            if self.xflip_armature and obj.type == "ARMATURE":
                obj.scale = (1.0, -1.0, 1.0)
                objFlipped = True
            if self.xflip_mesh and obj.type == "MESH":
                obj.scale = (1.0, -1.0, 1.0)
                bm.from_mesh(obj.data)
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                bm.to_mesh(obj.data)
                bm.clear()
                obj.data.update()
                objFlipped = True
            obj.select = True

        if objRotated is True or objFlipped is True:
            bpy.ops.object.transform_apply(rotation = objRotated, scale = objFlipped)

        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "global_scale",
                                            "check_existing",
                                            "filter_glob",
                                            "xna_validate",
                                            ))

        from . import export_dae
        result = export_dae.save(self, context, **keywords)

        objFlipped = False
        objRotated = False
        
        for obj in modifyObjects:
            if obj in rotatedObjects:
                obj.rotation_euler = (obj.rotation_euler.to_matrix() * Matrix.Rotation(radians(90), 3, 'X')).to_euler()
                objRotated = True
            if self.xflip_armature and obj.type == "ARMATURE":
                obj.scale = (-1.0, 1.0, 1.0)
                objFlipped = True
            if self.xflip_mesh and obj.type == "MESH":
                obj.scale = (-1.0, 1.0, 1.0)
                bm.from_mesh(obj.data)
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                bm.to_mesh(obj.data)
                bm.clear()
                obj.data.update()
                objFlipped = True
            obj.select = True

        if objRotated is True or objFlipped is True:
            bpy.ops.object.transform_apply(rotation = objRotated, scale = objFlipped)
        
        for obj in rotatedObjects:
            obj.rotation_euler = originalRotations[obj.name]
            print("Reverted object rotation for " + obj.name + " : " + str(originalRotations[obj.name]))
            #rotatedObjects.remove(obj)
        
        bpy.ops.object.select_all(action='DESELECT')
        
        for obj in selectedObjects:
            obj.select = True
        
        if activeObject is not None:
            bpy.context.scene.objects.active = activeObject
        
        # Return to previous mode
        if current_mode is not None and activeObject is not None:
            if activeObject.type != "ARMATURE" and current_mode == "POSE":
                bpy.ops.object.mode_set(mode="OBJECT")
            else:
                bpy.ops.object.mode_set ( mode = current_mode )
        else:
            bpy.ops.object.mode_set(mode="OBJECT")

        if self.convert_gr2:
            if (addon_prefs.lslib_path is not None and addon_prefs.lslib_path != "" 
                and os.path.isfile(addon_prefs.lslib_path)):
                    gr2_path = str.replace(self.filepath, ".dae", ".gr2")

                    gr2_options_str = self.build_gr2_options()

                    divine_exe = '"{}"'.format(addon_prefs.lslib_path)

                    proccess_args = "{} -g dos2 -s {} -d {} -i dae -o gr2 -a convert-model --gr2-options {}".format(
                        divine_exe, '"{}"'.format(self.filepath), '"{}"'.format(gr2_path), gr2_options_str
                    )
                    
                    print("Starting GR2 conversion using divine.exe.")
                    print("Sending command: {}".format(proccess_args))

                    process = subprocess.run(proccess_args, 
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

                    if process.returncode != 0:
                        raise Exception("Error converting DAE to GR2: \"{}\"".format(process.stderr))
                    else:
                        #Deleta .dae
                        print(process.stdout)

                        if self.divine_settings.delete_collada:
                            os.remove(self.filepath)
            else:
                raise Exception("[DOS2DE-Collada] LSLib not found. Cannot convert to GR2.")
           
        return result


def menu_func(self, context):
    self.layout.operator(ExportDAE.bl_idname,
                         text="DOS2DE Collada (.dae)")

addon_keymaps = []

def register():
    bpy.utils.register_module(__name__)
    #bpy.utils.register_class(ExportDAE)
    bpy.types.INFO_MT_file_export.append(menu_func)

    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new('Window', space_type='EMPTY', region_type='WINDOW', modal=False)

    kmi = km.keymap_items.new(ExportDAE.bl_idname, 'E', 'PRESS', ctrl=True, shift=True)
    #print(__name__)
    #kmi.properties.name = ExportDAE.bl_idname
    addon_keymaps.append((km, kmi))

def unregister():
    bpy.utils.unregister_module(__name__)
    #bpy.utils.unregister_class(ExportDAE)

    bpy.types.INFO_MT_file_export.remove(menu_func)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        for km, kmi in addon_keymaps:
            km.keymap_items.remove(kmi)
    addon_keymaps.clear()

if __name__ == "__main__":
    register()

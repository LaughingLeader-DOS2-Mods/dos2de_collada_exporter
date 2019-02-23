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
import addon_utils

from bpy.types import Operator, AddonPreferences, PropertyGroup, UIList
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty, CollectionProperty, PointerProperty, IntProperty

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

class ProjectData(PropertyGroup):
    project_folder = StringProperty(
        name="Project Folder",
        description="The root folder where .blend files are stored"
    )
    export_folder = StringProperty(
        name="Export Folder",
        description="The root export folder"
    )

class ProjectEntry(PropertyGroup):
    project_data = CollectionProperty(type=ProjectData)
    index = IntProperty()

class AddProjectOperator(Operator):
    bl_idname = "userpreferences.dos2de_settings_addproject"
    bl_label = "Add Project"
    bl_description = "Add an entry to the project list"

    def execute(self, context):
        user_preferences = context.user_preferences
        addon_prefs = user_preferences.addons[__name__].preferences
        project = addon_prefs.projects.project_data.add()
        return {'FINISHED'}

class RemoveProjectOperator(Operator):
    bl_idname = "userpreferences.dos2de_settings_removeproject"
    bl_label = "Remove"
    bl_description = "Remove Project"

    selected_project = CollectionProperty(type=ProjectData)

    def set_selected(self, item):
        selected_project = item

    def execute(self, context):
        user_preferences = context.user_preferences
        addon_prefs = user_preferences.addons[__name__].preferences

        i = 0
        for project in addon_prefs.projects.project_data:
            if (project.project_folder == self.selected_project[0].project_folder
                and project.export_folder == self.selected_project[0].export_folder):
                    addon_prefs.projects.project_data.remove(i)
            i += 1

        self.selected_project.clear()

        return {'FINISHED'}

class DivinityProjectList(UIList):
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            layout.prop(item, "project_folder", text="Project Folder")
            layout.prop(item, "export_folder", text="Export Folder")
            op = layout.operator("userpreferences.dos2de_settings_removeproject", icon="CANCEL", text="", emboss=False)
            #Is there no better way?
            project = op.selected_project.add()
            project.project_folder = item.project_folder
            project.export_folder = item.export_folder

        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon_value=icon)

class ExportColladaAddonPreferences(AddonPreferences):
    bl_idname = __name__

    lslib_path = StringProperty(
        name="Divine Path",
        description="The path to divine.exe, used to convert from dae to gr2",
        subtype='FILE_PATH',
    )
    gr2_default_enabled = BoolProperty(
        name="Convert to GR2 by Default",
        default=True,
        description="Models will be converted to gr2 by default if the Divine Path is set"
    )

    default_preset = EnumProperty(
        name="Default Preset",
        description="The default preset to load when the exporter is opened for the first time",
        items=(("NONE", "None", ""),
               ("MESHPROXY", "MeshProxy", "Use default meshproxy settings"),
               ("ANIMATION", "Animation", "Use default animation settings"),
               ("MODEL", "Model", "Use default model settings")),
        default=("NONE")
    )

    auto_export_subfolder = BoolProperty(
        name="Use Preset Type for Project Export Subfolder",
        description="If enabled, the export subfolder will be determined by the preset type set.\nFor instance, Models go into \Models",
        default=False
    )

    #projects = CollectionProperty(
    #    type=ExportColladaProjectPaths,
    #    name="Projects",
    #    description="Project pathways to auto-detect when exporting"
    #)

    projects = PointerProperty(
        type=ProjectEntry,
        name="Projects",
        description="Project pathways to auto-detect when exporting"
    )

    def draw(self, context):
        layout = self.layout
        layout.label(text="Divinity Export Addon Preferences")
        layout.prop(self, "lslib_path")
        layout.prop(self, "gr2_default_enabled")
        layout.prop(self, "default_preset")
        layout.prop(self, "auto_export_subfolder")

        layout.separator()
        layout.label("Projects")
        layout.template_list("DivinityProjectList", "", self.projects, "project_data", self.projects, "index")
        layout.operator("userpreferences.dos2de_settings_addproject")

class GR2_ExportSettings(bpy.types.PropertyGroup):
    """GR2 Export Options"""

    extra_flags = (
        ("DISABLED", "Disabled", ""),
        ("MESHPROXY", "MeshProxy", "Flags the mesh as a meshproxy, used for displaying overlay effects on a weapon and AllSpark MeshEmiters"),
        ("CLOTH", "Cloth", "The mesh has vertex painting for use with Divinity's cloth system"),
        ("RIGID", "Rigid", "For meshes lacking an armature modifier. Typically used for weapons")
    )

    extras = EnumProperty(
        name="Flag",
        description="Flag every mesh with the selected flag.\nNote: Custom Properties on a mesh will override this",
        items=extra_flags,
        default=("DISABLED")
    )
    yup_conversion = BoolProperty(
        name="Convert to Y-Up",
        default=False
    )
    apply_basis_transforms = BoolProperty(
        name="Apply Y-Up Transformations",
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
        obj.prop(self, "apply_basis_transforms")
        obj.prop(self, "force_legacy")
        obj.prop(self, "store_indices")
        obj.prop(self, "create_dummyskeleton")

        obj.label("Extra Properties (Global)")
        obj.prop(self, "extras")
        #extrasobj = obj.row(align=False)
        #self.extras.draw(context, extrasobj)

class Divine_ExportSettings(bpy.types.PropertyGroup):
    """Divine GR2 Conversion Settings"""
    gr2_settings = bpy.props.PointerProperty(
        type=GR2_ExportSettings,
        name="GR2 Export Options"
    )

    game_enums = (
        ("dos", "DOS", "Divinity: Original Sin"),
        ("dosee", "DOSEE", "Divinity: Original Sin - Enhanced Edition"),
        ("dos2", "DOS2", "Divinity: Original Sin 2"),
        ("dos2de", "DOS2DE", "Divinity: Original Sin 2 - Definitive Edition")
    )

    game = EnumProperty(
        name="Game",
        description="The target game. Currently determines the model format type",
        items=game_enums,
        default=("dos2de")
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

    navigate_to_blendfolder = BoolProperty(default=False)

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
        obj.prop(self, "game")
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

    export_directory = StringProperty(
        name="Project Export Directory",
        default="",
        options={"HIDDEN"}
    )

    use_metadata = BoolProperty(
        name="Use Metadata",
        default=True,
        options={"HIDDEN"}
        )

    auto_determine_path = BoolProperty(
        default=True,
        name="Auto-Path",
        description="Automatically determine the export path"
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

    initialized = BoolProperty(default=False)
    update_path_next = BoolProperty(default=False)
    log_message = StringProperty(options={"HIDDEN"})

    gr2_default_enabled_ignore = BoolProperty(default=False, options={"HIDDEN"})

    def build_gr2_options(self):
        export_str = ""
        # Possible args:
        #"export-normals;export-tangents;export-uvs;export-colors;deduplicate-vertices;
        # deduplicate-uvs;recalculate-normals;recalculate-tangents;recalculate-iwt;flip-uvs;
        # force-legacy-version;compact-tris;build-dummy-skeleton;apply-basis-transforms;conform"

        divine_args = {
            "xflip_skeletons"           : "x-flip-skeletons",
            "xflip_meshes"              : "x-flip-meshes",
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
            "yup_conversion"            : "y-up-skeletons",
            "apply_basis_transforms"    : "apply-basis-transforms"
            #"conform"					: "conform"
        }

        for prop,arg in divine_args.items():
            val = getattr(self.divine_settings, prop)
            if val == True:
                export_str += "-e " + arg + " "

        gr2_settings = self.divine_settings.gr2_settings

        for prop,arg in gr2_args.items():
            val = getattr(gr2_settings, prop)
            if val == True:
                export_str += "-e " + arg + " "

        return export_str;

    def update_filepath(self, context):
        if self.directory == "":
            self.directory = os.path.dirname(bpy.data.filepath)

        if self.filepath == "":
            #self.filepath = bpy.path.ensure_ext(str.replace(bpy.path.basename(bpy.data.filepath), ".blend", ""), self.filename_ext)
            self.filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, str.replace(bpy.path.basename(bpy.data.filepath), ".blend", "")), self.filename_ext)

        if self.filepath != "" and self.last_filepath == "":
            self.last_filepath = self.filepath

        user_preferences = context.user_preferences
        addon_prefs = user_preferences.addons[__name__].preferences
        
        if self.auto_determine_path == True and addon_prefs.auto_export_subfolder == True and self.export_directory != "":
            auto_directory = self.export_directory
            if self.selected_preset != "NONE":
                if self.selected_preset == "MODEL":
                    auto_directory = "{}\\{}".format(self.export_directory, "Models")
                elif self.selected_preset == "ANIMATION":
                    auto_directory = "{}\\{}".format(self.export_directory, "Animations")
                elif self.selected_preset == "MESHPROXY":
                    auto_directory = "{}\\{}".format(self.export_directory, "Proxy")
            
            if not os.path.exists(auto_directory):
                os.mkdir(auto_directory)
            self.directory = auto_directory
            self.update_path = True

        if self.filepath != "":
            if self.auto_name == "LAYER":
                if hasattr(bpy.data.scenes["Scene"], "namedlayers"):
                    for i in range(20):
                        if (bpy.data.scenes["Scene"].layers[i]):
                            self.auto_filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, 
                                                    bpy.data.scenes["Scene"].namedlayers.layers[i].name), 
                                                self.filename_ext)
                            self.update_path = True
                else:
                    self.log_message = "The 3D Layer Manager addon must be enabled before you can use layer names when exporting."
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
                    else:
                        #Blend name
                        self.auto_filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, str.replace(bpy.path.basename(bpy.data.filepath), ".blend", "")), self.filename_ext)
            elif self.auto_name == "DISABLED" and self.last_filepath != "":
                self.auto_filepath = self.last_filepath
                self.update_path = True
            #if self.update_path:
                #print("[DOS2DE] Filepath set to " + str(self.auto_filepath))
        return
 
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
        name="GR2 Settings"
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
        default={"EMPTY", "CAMERA", "LAMP", "ARMATURE", "MESH", "CURVE"}
    )

    use_export_selected = BoolProperty(
        name="Selected Only",
        description="Export only selected objects (and visible in active "
                    "layers if that applies).",
        default=False
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
        default=False
        )
    xflip_mesh = BoolProperty(
        name="X-Flip Mesh",
        description="Flips the mesh on the x-axis.",
        default=False
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
    use_normalize_vert_groups = BoolProperty(
        name="Normalize Vertex Groups",
        description="Normalize all vertex groups",
        default=True
        )
    use_tangent_arrays = BoolProperty(
        name="Tangent Arrays",
        description="Export Tangent and Binormal arrays "
                    "(for normalmapping).",
        default=True
        )
    use_triangles = BoolProperty(
        name="Triangulate",
        description="Export Triangles instead of Polygons.",
        default=True
        )

    use_copy_images = BoolProperty(
        name="Copy Images",
        description="Copy Images (create images/ subfolder)",
        default=False
        )
    use_active_layers = BoolProperty(
        name="Active Layers Only",
        description="Export only objects on the active layers.",
        default=True
        )
    use_exclude_ctrl_bones = BoolProperty(
        name="Exclude Control Bones",
        description=("Exclude skeleton bones with names beginning with 'ctrl' "
                     "or bones which are not marked as Deform bones."),
        default=True
        )
    use_anim = BoolProperty(
        name="Export Animation",
        description="Export keyframe animation",
        default=False
        )
    use_anim_action_all = BoolProperty(
        name="Export All Actions",
        description=("Export all actions for the first armature found "
                     "in separate DAE files"),
        default=False
        )
    use_anim_skip_noexp = BoolProperty(
        name="Skip (-noexp) Actions",
        description="Skip exporting of actions whose name end in (-noexp)."
                    " Useful to skip control animations.",
        default=True
        )
    use_anim_optimize = BoolProperty(
        name="Optimize Keyframes",
        description="Remove double keyframes",
        default=True
        )

    use_shape_key_export = BoolProperty(
        name="Export Shape Keys",
        description="Export shape keys for selected objects.",
        default=False
        )
        
    anim_optimize_precision = FloatProperty(
        name="Precision",
        description=("Tolerence for comparing double keyframes "
                     "(higher for greater accuracy)"),
        min=1, max=16,
        soft_min=1, soft_max=16,
        default=6.0
        )

    # Used to reset the global extra flag when a preset is changed
    preset_applied_extra_flag = BoolProperty(default=False)
    preset_last_extra_flag = EnumProperty(items=GR2_ExportSettings.extra_flags, default=("DISABLED"))
       
    def apply_preset(self, context):

        if self.initialized:
            #bpy.data.window_managers['dos2de_lastpreset'] = str(self.selected_preset)
            bpy.context.scene['dos2de_lastpreset'] = self.selected_preset

        if self.selected_preset == "NONE":
            if self.preset_applied_extra_flag:
                if self.preset_last_extra_flag != "DISABLED":
                    self.divine_settings.gr2_settings.extras = self.preset_last_extra_flag
                    self.preset_last_extra_flag = "DISABLED"
                    print("Reverted extras flag to {}".format(self.divine_settings.gr2_settings.extras))
                else:
                    self.divine_settings.gr2_settings.extras = "DISABLED"
                self.preset_applied_extra_flag = False
            return
        elif self.selected_preset == "MODEL":
            self.object_types = {"ARMATURE", "MESH"}
            self.yup_enabled = "ROTATE"
            self.use_normalize_vert_groups = True
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

            if self.preset_applied_extra_flag:
                if self.preset_last_extra_flag != "DISABLED":
                    self.divine_settings.gr2_settings.extras = self.preset_last_extra_flag
                    self.preset_last_extra_flag = "DISABLED"
                    print("Reverted extras flag to {}".format(self.divine_settings.gr2_settings.extras))
                else:
                    self.divine_settings.gr2_settings.extras = "DISABLED"
                self.preset_applied_extra_flag = False

        elif self.selected_preset == "ANIMATION":
            self.object_types = {"ARMATURE"}
            self.yup_enabled = "ROTATE"
            self.use_normalize_vert_groups = False
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

            if (self.preset_applied_extra_flag == False):
                if(self.preset_last_extra_flag == "DISABLED" and self.divine_settings.gr2_settings.extras != "DISABLED"):
                    self.preset_last_extra_flag = self.divine_settings.gr2_settings.extras
                self.preset_applied_extra_flag = True
            
            self.divine_settings.gr2_settings.extras = "DISABLED"

        elif self.selected_preset == "MESHPROXY":
            self.object_types = {"MESH"}
            self.yup_enabled = "ROTATE"
            self.use_normalize_vert_groups = True
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

            if (self.preset_applied_extra_flag == False):
                if(self.preset_last_extra_flag == "DISABLED" and self.divine_settings.gr2_settings.extras != "DISABLED"):
                    self.preset_last_extra_flag = self.divine_settings.gr2_settings.extras
                self.preset_applied_extra_flag = True
            
            self.divine_settings.gr2_settings.extras = "MESHPROXY"

        if self.initialized:
            self.update_path_next = True

        return
        #self.selected_preset = "NONE"

    selected_preset = EnumProperty(
        name="Preset",
        description="Use a built-in preset.",
        items=(("NONE", "None", ""),
               ("MESHPROXY", "MeshProxy", "Use default meshproxy settings"),
               ("ANIMATION", "Animation", "Use default animation settings"),
               ("MODEL", "Model", "Use default model settings")),
        default=("NONE"),
        update=apply_preset
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
        col.prop(self, "auto_determine_path")
        col.prop(self, "selected_preset")

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
        col.prop(self, "use_normalize_vert_groups")

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

        if self.log_message != "":
            print(self.log_message)
            self.report({'WARNING'}, "{}".format(self.log_message))
            self.log_message = ""

        user_preferences = context.user_preferences
        addon_prefs = user_preferences.addons[__name__].preferences

        if self.convert_gr2 == False:
            self.gr2_default_enabled_ignore = True
        elif self.gr2_default_enabled_ignore == True:
            self.gr2_default_enabled_ignore = False

        update = False

        if self.divine_settings.navigate_to_blendfolder == True:
            self.directory = os.path.dirname(bpy.data.filepath)
            self.filepath = "" #reset
            self.update_path_next = True
            self.divine_settings.navigate_to_blendfolder = False

        if(self.update_path_next):
            self.update_filepath(context)
            self.update_path_next = False
        
        if self.update_path:
            update = True
            self.update_path = False
            if self.filepath != self.auto_filepath:
                self.filepath = bpy.path.ensure_ext(self.auto_filepath, self.filename_ext)
                #print("[DOS2DE] Filepath is actually: " + self.filepath)

        return update
        
    def invoke(self, context, event):
        user_preferences = context.user_preferences
        addon_prefs = user_preferences.addons[__name__].preferences

        if addon_prefs.gr2_default_enabled == True and self.gr2_default_enabled_ignore == False:
            self.convert_gr2 = True

        saved_preset = bpy.context.scene.get('dos2de_lastpreset', None)

        if saved_preset is not None:
            self.selected_preset = saved_preset
        else:
            if addon_prefs.default_preset != "NONE":
                self.selected_preset = addon_prefs.default_preset

        if self.filepath != "" and self.last_filepath == "":
            self.last_filepath = self.filepath

        if addon_prefs.projects and self.auto_determine_path == True:
            projects = addon_prefs.projects.project_data
            if projects:
                for project in projects:
                    project_folder = project.project_folder
                    export_folder = project.export_folder

                    print("Checking {} for {}".format(self.filepath, project_folder))

                    if(export_folder != "" and project_folder != "" and 
                        bpy.path.is_subdir(self.filepath, project_folder)):
                            self.export_directory = export_folder
                            self.directory = export_folder
                            self.filepath = export_folder
                            self.last_filepath = self.filepath
                            print("Setting start path to export folder: \"{}\"".format(export_folder))
                            break

        self.update_filepath(context)
        context.window_manager.fileselect_add(self)

        self.initialized = True

        return {'RUNNING_MODAL'}

    def execute(self, context):
        if not self.filepath:
            raise Exception("filepath not set")
        
        user_preferences = context.user_preferences
        addon_prefs = user_preferences.addons[__name__].preferences

        if hasattr(bpy.context, "object") and hasattr(bpy.context.object, "mode"):
            current_mode = bpy.context.object.mode
        else:
            current_mode = "OBJECT"

        activeObject = None
        if bpy.context.scene.objects.active:
            activeObject = bpy.context.scene.objects.active

        if self.xflip_mesh:
            bm = bmesh.new()
        
        modifyObjects = []
        selectedObjects = []
        originalRotations = {}

        bpy.ops.object.mode_set(mode="OBJECT")
        
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

        if self.yup_enabled == "ROTATE":
            for obj in modifyObjects:
                originalRotations[obj.name] = obj.rotation_euler.copy()
                print("Saved rotation for " + obj.name + " : " + str(originalRotations[obj.name]))

        for obj in modifyObjects:
            obj_rotated = False
            obj_flipped = False

            if self.yup_enabled == "ROTATE":
                if not obj.parent:
                    obj.rotation_euler = (obj.rotation_euler.to_matrix() * Matrix.Rotation(radians(-90), 3, 'X')).to_euler()
                    print("Rotated " + obj.name + " : " + str(obj.rotation_euler))
                    obj_rotated = True
                elif obj.parent.get('dosde_rotated', False) == True:
                    #Child objects will have a new rotation after their parents have applied
                    bpy.context.scene.objects.active = obj
                    bpy.ops.object.mode_set(mode="OBJECT")
                    bpy.ops.object.transform_apply(rotation = True)
                    #obj_rotated = True

            if self.xflip_armature and obj.type == "ARMATURE":
                obj.scale = (1.0, -1.0, 1.0)
                obj_flipped = True
            if self.xflip_mesh and obj.type == "MESH":
                obj.scale = (1.0, -1.0, 1.0)
                bm.from_mesh(obj.data)
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                bm.to_mesh(obj.data)
                bm.clear()
                obj.data.update()
                obj_flipped = True
            
            #obj.select = True
            obj['dosde_rotated'] = obj_rotated
            obj['dosde_flipped'] = obj_flipped

            if obj_rotated or obj_flipped:
                bpy.context.scene.objects.active = obj
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.transform_apply(rotation = obj_rotated, scale = obj_flipped)
                print("Applied transformations for {}.".format(obj.name))

            if self.use_normalize_vert_groups and obj.type == "MESH":
                bpy.context.scene.objects.active = obj
                bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
                bpy.ops.object.vertex_group_normalize_all()
                bpy.ops.object.mode_set(mode="OBJECT")
                print("Normalized vertex groups for {}.".format(obj.name))

        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "global_scale",
                                            "check_existing",
                                            "filter_glob",
                                            "xna_validate",
                                            ))

        from . import export_dae
        result = export_dae.save(self, context, **keywords)


        for obj in modifyObjects:
            
            obj_rotated = obj.get("dosde_rotated", False)
            obj_flipped = obj.get("dos2de_flipped", False)

            print("{} is rotated: {} flipped: {}".format(obj.name, obj_rotated, obj_flipped))

            if obj_rotated:
                obj.rotation_euler = (obj.rotation_euler.to_matrix() * Matrix.Rotation(radians(90), 3, 'X')).to_euler()
                #print("Reverted object rotation for {}".format(obj.name))

            if obj_flipped:
                if obj.type == "ARMATURE":
                    obj.scale = (-1.0, 1.0, 1.0)
                    obj["dos2de_flipped"] = False
                if obj.type == "MESH":
                    obj.scale = (-1.0, 1.0, 1.0)
                    bm.from_mesh(obj.data)
                    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                    bm.to_mesh(obj.data)
                    bm.clear()
                    obj.data.update()
                
            if obj_rotated or obj_flipped:
                bpy.context.scene.objects.active = obj
                bpy.ops.object.mode_set(mode="OBJECT")
                bpy.ops.object.transform_apply(rotation = obj_rotated, scale = obj_flipped)

            if obj.name in originalRotations:
                obj.rotation_euler = originalRotations[obj.name]
                print("Reverted object rotation for {} : {}".format(obj.name, originalRotations[obj.name]))

            obj['dosde_rotate'] = False
            obj['dosde_flippe'] = False
            
            obj.select = False
        
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

                    proccess_args = "{} --loglevel all -g {} -s {} -d {} -i dae -o gr2 -a convert-model {}".format(
                        divine_exe, self.divine_settings.game, '"{}"'.format(self.filepath), '"{}"'.format(gr2_path), gr2_options_str
                    )
                    
                    print("Starting GR2 conversion using divine.exe.")
                    print("Sending command: {}".format(proccess_args))

                    process = subprocess.run(proccess_args, 
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

                    print(process.stdout)
                    
                    if process.returncode != 0:
                        #raise Exception("Error converting DAE to GR2: \"{}\"{}".format(process.stderr, process.stdout))
                        error_message = "[DOS2DE-Collada] [ERROR:{}] Error converting DAE to GR2. {}".format(process.returncode, '\n'.join(process.stdout.splitlines()[-1:]))
                        self.report({"ERROR"}, error_message)
                        print(error_message)
                    else:
                        #Deleta .dae
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

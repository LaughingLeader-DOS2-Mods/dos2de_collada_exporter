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

from bpy.app.handlers import persistent

from math import radians, degrees
from mathutils import Euler, Matrix

from . import export_dae

bl_info = {
    "name": "Divinity Collada Exporter",
    "author": "LaughingLeader",
    "blender": (2, 7, 9),
    "api": 38691,
    "location": "File > Import-Export",
    "description": ("Export Collada/Granny files for Divinity: Original Sin 2 - Definitive Edition."),
    "warning": "",
    "wiki_url": (""),
    "tracker_url": "",
    "support": "COMMUNITY",
    "category": "Import-Export"}

if "bpy" in locals():
    import imp
    if "export_dae" in locals():
        imp.reload(export_dae) # noqa

gr2_extra_flags = (
    ("DISABLED", "Disabled", ""),
    ("MESHPROXY", "MeshProxy", "Flags the mesh as a meshproxy, used for displaying overlay effects on a weapon and AllSpark MeshEmiters"),
    ("CLOTH", "Cloth", "The mesh has vertex painting for use with Divinity's cloth system"),
    ("RIGID", "Rigid", "For meshes lacking an armature modifier. Typically used for weapons"),
    ("RIGIDCLOTH", "Rigid&Cloth", "For meshes lacking an armature modifier that also contain cloth physics. Typically used for weapons")
)

class ExportProgressProperties(PropertyGroup):
    progress_total = IntProperty(name="Progress Total", options={"HIDDEN"})
    progress_message = StringProperty(name="Progress Message", options={"HIDDEN"}, default="{}{}")
    progress_finished = BoolProperty(options={"HIDDEN"})
    progress_display_text = StringProperty(name="Progress Message", options={"HIDDEN"}, default="")

    def update_progress_text(self, context):
        if self.progress_total > 0:
            if self.progress_finished == False:
                self.progress_display_text = self.progress_message.format(self.progress_current, self.progress_total)
            else:
                self.progress_display_text = self.progress_message
        else:
            self.progress_display_text = ""
        
        #print("Updated progress? {}".format(self.progress_display_text))

    progress_current = IntProperty(name="Current Progress", options={"HIDDEN"}, update=update_progress_text)

def start_progress(total, text=''):
    return
    progress = bpy.context.scene.daefileprogress
    progress.progress_current = 0
    progress.progress_total = total
    progress.progress_finished = False

    if text != "":
        progress.progress_message = text
    else:
        progress.progress_message = "Processing... {}/{}"

def update_progress(inc, text=""):
    return
    progress = bpy.context.scene.daefileprogress
    if progress.progress_finished == False:
        progress.progress_current += inc
        if progress.progress_current > progress.progress_total:
            progress.progress_finished = True

    if text != "":
        progress.progress_message = text

def finish_progress(text=""):
    return
    progress = bpy.context.scene.daefileprogress
    progress.progress_finished = True
    if text != "":
        progress.progress_message = text

def draw_file_progress(self, context):
    self.layout.prop(bpy.context.scene.daefileprogress, "progress_display_text", emboss=False, text="", expand=True)

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
        addon_prefs = user_preferences.addons["io_scene_dos2de"].preferences
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
        addon_prefs = user_preferences.addons["io_scene_dos2de"].preferences

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
    bl_idname = "io_scene_dos2de"

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

class GR2_ExportSettings(PropertyGroup):
    """GR2 Export Options"""

    extras = EnumProperty(
        name="Flag",
        description="Flag every mesh with the selected flag.\nNote: Custom Properties on a mesh will override this",
        items=gr2_extra_flags,
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

class Divine_ExportSettings(PropertyGroup):
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
    ignore_uv_nan = BoolProperty(
        name="Ignore Bad NaN UVs",
        description="Ignore bad/unwrapped UVs that fail to form a triangle. Export will fail if these are detected",
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
            "ignore_uv_nan",
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

    filter_glob = StringProperty(default="*.dae;*.gr2", options={"HIDDEN"})
    
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
            "flip_uvs"                  : "flip-uvs",
            "ignore_uv_nan"             : "ignore-uv-nan"
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
        addon_prefs = user_preferences.addons["io_scene_dos2de"].preferences

        next_path = ""

        if self.filepath != "":
            if self.auto_name == "LAYER":
                if "namedlayers" in bpy.data.scenes[context.scene.name]:
                    namedlayers = getattr(bpy.data.scenes[context.scene.name], "namedlayers", None)
                    if namedlayers is not None:
                        #print("ACTIVE_LAYER: {}".format(context.scene.active_layer))
                        if (bpy.data.scenes[context.scene.name].layers[context.scene.active_layer]):
                                next_path = namedlayers.layers[context.scene.active_layer].name
                else:
                    self.log_message = "The 3D Layer Manager addon must be enabled before you can use layer names when exporting."
            elif self.auto_name == "ACTION":
                armature = None
                if self.use_active_layers:
                    obj = next(iter([x for x in context.scene.objects if x.type == "ARMATURE" and x.layers[context.scene.active_layer]]))
                    if obj is not None:
                        armature = obj
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
                        next_path = anim_name
                    else:
                        #Blend name
                        next_path = str.replace(bpy.path.basename(bpy.data.filepath), ".blend", "")
            elif self.auto_name == "DISABLED" and self.last_filepath != "":
                self.auto_filepath = self.last_filepath

        if self.auto_determine_path == True and addon_prefs.auto_export_subfolder == True and self.export_directory != "":
            auto_directory = self.export_directory
            if self.selected_preset != "NONE":
                if self.selected_preset == "MODEL":
                    if "_FX_" in next_path:
                        auto_directory = "{}\\Models\\Effects".format(self.export_directory)
                    else:
                        auto_directory = "{}\\{}".format(self.export_directory, "Models")
                elif self.selected_preset == "ANIMATION":
                    auto_directory = "{}\\{}".format(self.export_directory, "Animations")
                elif self.selected_preset == "MESHPROXY":
                    auto_directory = "{}\\{}".format(self.export_directory, "Proxy")
            
            if not os.path.exists(auto_directory):
                os.mkdir(auto_directory)
            self.directory = auto_directory
            self.update_path = True
        
        print("Dir export_directory({}) self.directory({})".format(self.export_directory, self.directory))

        if next_path != "":
            self.auto_filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, next_path), self.filename_ext)
            self.update_path = True

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
        items=(
               ("ARMATURE", "Armature", ""),
               ("MESH", "Mesh", ""),
               ("MATERIAL", "Material", "Export the material for each mesh"),
               ("CURVE", "Curve", ""),
               ("EMPTY", "Empty", ""),
        ),
        default={"ARMATURE", "MESH", "MATERIAL", "EMPTY", "MESH", "CURVE"}
    )

    use_export_selected = BoolProperty(
        name="Selected Only",
        description="Export only selected objects (and visible in active "
                    "layers if that applies).",
        default=False
        )

    use_export_visible = BoolProperty(
        name="Visible Only",
        description="Export only visible, unhidden, selectable objects",
        default=True
        )

    yup_rotation_options = (
        ("DISABLED", "Disabled", ""),
        ("ROTATE", "Rotate", "Rotate the object towards y-up"),
        ("ACTION", "Flag", "Flag the object as being y-up without rotating it")
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
    use_tangent = BoolProperty(
        name="Export Tangents",
        description="Export Tangent and Binormal arrays (for normalmapping).",
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
    anim_export_all_separate = BoolProperty(
        name="Export All Actions",
        description="Export all actions as separate animation files",
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

    applying_preset = BoolProperty(default=False)
    yup_local_override = BoolProperty(default=False)

    def yup_local_override_save(self, context):
        if self.applying_preset is not True:
            self.yup_local_override = True
            bpy.context.scene['dos2de_yup_local_override'] = self.yup_enabled

    yup_enabled = EnumProperty(
        name="Y-Up",
        description="Converts from Z-up to Y-up.",
        items=yup_rotation_options,
        default=("DISABLED"),
        update=yup_local_override_save
        )

    # Used to reset the global extra flag when a preset is changed
    preset_applied_extra_flag = BoolProperty(default=False)
    preset_last_extra_flag = EnumProperty(items=gr2_extra_flags, default=("DISABLED"))
       
    def apply_preset(self, context):
        if self.initialized:
            #bpy.data.window_managers['dos2de_lastpreset'] = str(self.selected_preset)
            bpy.context.scene['dos2de_lastpreset'] = self.selected_preset
            self.applying_preset = True

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
            #self.object_types = {"ARMATURE", "MESH", "MATERIAL"}
            self.object_types = {"ARMATURE", "MESH"}

            if self.yup_local_override is False:
                self.yup_enabled = "ROTATE"
            self.use_normalize_vert_groups = True
            self.use_tangent = True
            self.use_triangles = True
            self.use_active_layers = True
            self.auto_name = "LAYER"

            self.xflip_armature = False
            self.xflip_mesh = False
            self.use_copy_images = False
            self.use_exclude_ctrl_bones = False
            self.use_anim = False
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
            if self.yup_local_override is False:
                self.yup_enabled = "ROTATE"
            self.use_normalize_vert_groups = False
            self.use_tangent = False
            self.use_triangles = False
            self.use_active_layers = True
            self.auto_name = "ACTION"

            self.xflip_armature = False
            self.xflip_mesh = False
            self.use_copy_images = False
            self.use_exclude_ctrl_bones = True
            self.use_anim = True
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
            if self.yup_local_override is False:
                self.yup_enabled = "ROTATE"
            self.use_normalize_vert_groups = True
            self.use_tangent = True
            self.use_triangles = True
            self.use_active_layers = True
            self.auto_name = "LAYER"

            self.xflip_armature = False
            self.xflip_mesh = False
            self.use_copy_images = False
            self.use_exclude_ctrl_bones = False
            self.use_anim = False
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

    batch_mode = BoolProperty(
        name="Batch Export",
        description="Export all active layers as separate files, or every action as separate animation files",
        default=False)

    debug_mode = BoolProperty(default=False, options={"HIDDEN"})

    def draw(self, context):
        layout = self.layout
        
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "object_types")

        col = layout.column(align=True)
        col.prop(self, "auto_determine_path")
        col.prop(self, "selected_preset")
        col.prop(self, "batch_mode")

        box = layout.box()
        box.prop(self, "auto_name")
        box.prop(self, "yup_enabled")
       
        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "use_active_layers")
        row.prop(self, "use_export_visible")
        row.prop(self, "use_export_selected")

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "use_tangent")
        row.prop(self, "use_triangles")
        col.prop(self, "use_normalize_vert_groups")

        col = layout.column(align=True)
        row = col.row(align=True)
        row.prop(self, "use_mesh_modifiers")
        if self.use_mesh_modifiers:
            row.prop(self, "use_exclude_armature_modifier")

        #col = layout.column(align=True)
        #row = col.row(align=True)
        #row.prop(self, "xflip_armature")
        #row.prop(self, "xflip_mesh")

        box = layout.box()
        box.prop(self, "use_anim")
        if self.use_anim:
            box.label("Animation Settings")
            if self.debug_mode:
                box.prop(self, "anim_export_all_separate")
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
        self.applying_preset = False

        if self.log_message != "":
            print(self.log_message)
            self.report({'WARNING'}, "{}".format(self.log_message))
            self.log_message = ""

        user_preferences = context.user_preferences
        addon_prefs = user_preferences.addons["io_scene_dos2de"].preferences

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
        addon_prefs = user_preferences.addons["io_scene_dos2de"].preferences

        blend_path = bpy.data.filepath
        print("Blend path: {} ".format(blend_path))

        if addon_prefs.gr2_default_enabled == True and self.gr2_default_enabled_ignore == False:
            self.convert_gr2 = True

        saved_preset = bpy.context.scene.get('dos2de_lastpreset', None)

        if saved_preset is not None:
            self.selected_preset = saved_preset
        else:
            if addon_prefs.default_preset != "NONE":
                self.selected_preset = addon_prefs.default_preset

        if "laughingleader_blender_helpers" in context.user_preferences.addons:
            helper_preferences = context.user_preferences.addons["laughingleader_blender_helpers"].preferences
            if helper_preferences is not None:
                self.debug_mode = getattr(helper_preferences, "debug_mode", False)
        #print("Preset: \"{}\"".format(self.selected_preset))

        # Multiple meshes tend to need different materials for programs like Substance Painter
        if self.selected_preset == "MODEL" and self.convert_gr2 == False:
            num_meshes = 0

            if self.use_active_layers:
                for i in range(20):
                    if context.scene.layers[i]:
                        for obj in context.scene.objects:
                            if obj.layers[i] and obj.type == "MESH":
                                num_meshes += 1
            elif self.use_export_selected:
                for obj in context.scene.objects:
                    if obj.select and obj.type == "MESH":
                        num_meshes += 1
            else:
                for obj in context.scene.objects:
                    if obj.type == "MESH":
                        num_meshes += 1
            
            print("Total Meshes: \"{}\"".format(num_meshes))

            if num_meshes > 1:
                self.object_types = {"ARMATURE", "MESH", "MATERIAL"}

        yup_local_override = bpy.context.scene.get('dos2de_yup_local_override', None)

        if yup_local_override is not None:
            self.yup_enabled = yup_local_override

        if self.filepath != "" and self.last_filepath == "":
            self.last_filepath = self.filepath

        if addon_prefs.projects and self.auto_determine_path == True:
            projects = addon_prefs.projects.project_data
            if projects:
                for project in projects:
                    project_folder = project.project_folder
                    export_folder = project.export_folder

                    print("Checking {} for {}".format(blend_path, project_folder))

                    if(export_folder != "" and project_folder != "" and 
                        bpy.path.is_subdir(blend_path, project_folder)):
                            self.export_directory = export_folder
                            self.directory = export_folder
                            self.filepath = export_folder
                            self.last_filepath = self.filepath
                            print("Setting start path to export folder: \"{}\"".format(export_folder))
                            break

        #bpy.types.FILEBROWSER_HT_header.append(draw_file_progress)

        self.update_filepath(context)
        context.window_manager.fileselect_add(self)

        self.initialized = True

        return {'RUNNING_MODAL'}

    def can_modify_object(self, context, obj):
        if self.use_export_visible and obj.hide or obj.hide_select:
            return False
        if self.use_export_selected and obj.select == False:
            return False
        if self.use_active_layers:
            for i in range(20):
                if context.scene.layers[i] and not obj.layers[i]:
                    return False
        return True

    def merge_armatures(self, context, modifyObjects):
        if len(context.scene.llexportmerge.armatures) <= 1:
            print("[DOS2DE-Export] [Warning] Only 1 object to merge. Skipping.")
            return modifyObjects
        merge_targets = []
        for objp in context.scene.llexportmerge.armatures:
            for obj in modifyObjects:
                name = obj.llexportprops.original_name
                if name == objp.name:
                    merge_targets.append(obj)
                    break
                else:
                    if len(obj.children) > 0:
                        target_obj = next((child for child in obj.children if child.name == name), None)
                        if target_obj is not None:
                            merge_targets.append(target_obj)
                            break

        count = len(merge_targets)
        if count > 1:
            top_object = merge_targets[0]
            top_object.select = True

            print("[DOS2DE-Export] Selected: {}".format(top_object.name))

            i = 1
            while i < count:
                obj = merge_targets[i]
                obj.select = True
                if obj in modifyObjects:
                    modifyObjects.remove(obj)
                print("[DOS2DE-Export] Selecting {} for merging with object {}".format(obj.name, top_object.name))
                selected = True
                i+=1

            bpy.context.scene.objects.active = top_object
            bpy.ops.object.join()

            print("[DOS2DE-Export] Merged selected objects for {}".format(top_object.name))

            bpy.ops.object.select_all(action='DESELECT')
            merge_targets.clear()
            top_object.select = False
            if top_object not in modifyObjects:
                modifyObjects.append(top_object)
        else:
            print("[DOS2DE-Export] [Error] No objects were selected for merge with {}")
        return modifyObjects

    def merge_meshes(self, context, modifyObjects):
        if len(context.scene.llexportmerge.meshes) <= 1:
            print("[DOS2DE-Export] [Warning] Only 1 object to merge. Skipping.")
            return modifyObjects
        merge_targets = []
        for objp in context.scene.llexportmerge.meshes:
            for obj in modifyObjects:
                name = obj.llexportprops.original_name
                if name == objp.name:
                    merge_targets.append(obj)
                    break
                else:
                    if len(obj.children) > 0:
                        target_obj = next((child for child in obj.children if child.name == name), None)
                        if target_obj is not None:
                            merge_targets.append(target_obj)
                            break

        count = len(merge_targets)
        if count > 1:
            top_object = merge_targets[0]
            top_object.select = True

            print("[DOS2DE-Export] Selected: {}".format(top_object.name))
            extra_flag = ""

            if "rigid" in top_object:
                extra_flag = "rigid"
            elif "cloth" in top_object:
                extra_flag = "cloth"
            elif "meshproxy" in top_object:
                extra_flag = "meshproxy"
            elif "rigidcloth" in top_object:
                extra_flag = "rigidcloth"

            i = 1
            while i < count:
                obj = merge_targets[i]
                #target_obj = next((x for x in modifyObjects if x.llexportprops.original_name == objname), None)
                obj.select = True
                if obj in modifyObjects:
                    modifyObjects.remove(obj)
                print("[DOS2DE-Export] Selecting {} for merging with object {}".format(obj.name, top_object.name))
                selected = True

                if extra_flag == "":
                    if "rigid" in obj:
                        extra_flag = "rigid"
                    elif "cloth" in obj:
                        extra_flag = "cloth"
                    elif "meshproxy" in obj:
                        extra_flag = "meshproxy"
                    elif "rigidcloth" in obj:
                        extra_flag = "rigidcloth"
                i+=1

            bpy.context.scene.objects.active = top_object
            bpy.ops.object.join()

            if extra_flag != "":
                if extra_flag == "rigid":
                    top_object["rigid"] = True
                elif extra_flag == "cloth":
                    top_object["cloth"] = True
                elif extra_flag == "meshproxy":
                    top_object["meshproxy"] = True
                elif extra_flag == "rigidcloth":
                    top_object["rigidcloth"] = True

                print("[DOS2DE-Export] Merged selected objects for {}".format(top_object.name))
            else:
                print("[DOS2DE-Export] [Error] No objects were selected for merge with {}".format(top_object.name))
            bpy.ops.object.select_all(action='DESELECT')
            merge_targets.clear()
            top_object.select = False

            if top_object not in modifyObjects:
                modifyObjects.append(top_object)
        else:
            print("[DOS2DE-Export] [Error] No objects were selected for merge with {}".format(top_object.name))
        return modifyObjects
    
    def transform_apply(self, context, obj, location=False, rotation=False, scale=False):
        last_active = getattr(bpy.context.scene.objects, "active", None)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.scene.objects.active = obj
        obj.select = True
        bpy.ops.object.mode_set(mode="OBJECT")
        bpy.ops.object.transform_apply(location=location, rotation=rotation, scale=scale)
        obj.select = False
        bpy.context.scene.objects.active = last_active

    def copy_obj(self, context, obj, parent=None):
        copy = obj.copy()
        copy.data = obj.data.copy()
        copy.llexportprops.copy(obj.llexportprops)

        context.scene.objects.link(copy)
        
        if hasattr(obj, "llexportprops"):
            copy.llexportprops.original_name = obj.name

        print("[DOS2DE-Export] Created a copy of object/data {} ({}/{})".format(obj.name, copy.name, copy.data.name))

        if parent is not None:
            copy.parent = parent
            copy.matrix_parent_inverse = obj.matrix_parent_inverse.copy()
            if parent.type == "ARMATURE":
                armature_modifiers = (mod for mod in copy.modifiers if mod.type == "ARMATURE" and 
                    obj.parent is not None and mod.object is not None and mod.object.name == obj.parent.name)
                for mod in armature_modifiers:
                    mod.object = parent
                    print("   [DOS2DE-Export] Updated armature modifier to point to the copied armature {} for child {}".format(parent.name, copy.name))

        return copy

    def cancel(self, context):
        #bpy.types.FILEBROWSER_HT_header.remove(draw_file_progress)
        pass

    def execute(self, context):
        if not self.filepath:
            raise Exception("filepath not set")
        
        user_preferences = context.user_preferences
        addon_prefs = user_preferences.addons["io_scene_dos2de"].preferences

        if bpy.context.object is not None and bpy.context.object.mode is not None:
            current_mode = bpy.context.object.mode
        else:
            current_mode = "OBJECT"

        activeObject = None
        if bpy.context.scene.objects.active:
            activeObject = bpy.context.scene.objects.active

        if self.xflip_mesh:
            bm = bmesh.new()
        
        targetObjects = []
        modifyObjects = []
        selectedObjects = []
        copies = []

        if activeObject is not None:
            bpy.ops.object.mode_set(mode="OBJECT")
        
        for obj in context.scene.objects:
            if obj.select:
                selectedObjects.append(obj)
                obj.select = False
            if self.can_modify_object(context, obj):
                targetObjects.append(obj)

        for obj in targetObjects:
            if not obj.parent:
                copy = self.copy_obj(context, obj)
                modifyObjects.append(copy)
                copies.append(copy)

                for childobj in obj.children:
                    if self.can_modify_object(context, childobj):
                        childcopy = self.copy_obj(context, childobj, copy)
                        modifyObjects.append(childcopy)
                        copies.append(childcopy)

        merging_enabled = hasattr(context.scene, "llexportmerge")

        for obj in modifyObjects:
            if hasattr(obj, "llexportprops"):
                if not obj.parent:
                    print("Preparing export properties for {}".format(obj.name))
                    obj.llexportprops.prepare(context, obj)
                    for childobj in obj.children:
                        print("  Preparing export properties for child {}".format(childobj.name))
                        childobj.llexportprops.prepare(context, childobj)

            if self.yup_enabled == "ROTATE":
                    if not obj.parent:
                        print("  Rotating {} to y-up. | (x={}, y={}, z={})".format(obj.name, degrees(obj.rotation_euler[0]),
                                    degrees(obj.rotation_euler[1]), degrees(obj.rotation_euler[2]))
                                )
                        obj.rotation_euler = (obj.rotation_euler.to_matrix() * Matrix.Rotation(radians(-90), 3, 'X')).to_euler()
                        print("  Rotated {} to y-up. | (x={}, y={}, z={})".format(obj.name, degrees(obj.rotation_euler[0]),
                                    degrees(obj.rotation_euler[1]), degrees(obj.rotation_euler[2]))
                                )

                        self.transform_apply(context, obj, rotation=True)

                        for childobj in obj.children:
                            childobj.select = True
                            # rot_x = degrees(childobj.rotation_euler[0])
                            # if rot_x != 0:
                            #     parent_yup_applied = round(rot_x) == -90
                            #     print("  Applying rotation transform to child {} | (x={})".format(childobj.name, rot_x))
                            #     self.transform_apply(context, childobj, rotation=True)

                            #     if parent_yup_applied == False:
                            #         print("    Rotating child to y-up: (x={}, y={}, z={})".format(degrees(childobj.rotation_euler[0]),
                            #                 degrees(childobj.rotation_euler[1]), degrees(childobj.rotation_euler[2]))
                            #             )
                            #         childobj.rotation_euler = (childobj.rotation_euler.to_matrix() * Matrix.Rotation(radians(-90), 3, 'X')).to_euler()
                            #         print("      Rotated child {} to y-up. (x={})".format(childobj.name, degrees(childobj.rotation_euler[0])))
                            #         self.transform_apply(context, childobj, rotation=True)

                        bpy.context.scene.objects.active = obj
                        obj.select = True
                        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
                        bpy.ops.object.select_all(action='DESELECT')

                        print(" {} Final (x={}, y={}, z={})".format(obj.name, degrees(obj.rotation_euler[0]),
                                    degrees(obj.rotation_euler[1]), degrees(obj.rotation_euler[2]))
                                )
            if self.xflip_armature and obj.type == "ARMATURE":
                obj.scale = (1.0, -1.0, 1.0)
                self.transform_apply(context, obj, scale=True)
                print("Flipped and applied scale transformation for {} ".format(obj.name))

            if self.xflip_mesh and obj.type == "MESH":
                obj.scale = (1.0, -1.0, 1.0)
                bm.from_mesh(obj.data)
                bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
                bm.to_mesh(obj.data)
                bm.clear()
                obj.data.update()
                self.transform_apply(context, obj, scale=True)
                print("Flipped and applied scale transformation for {} ".format(obj.name))

            if self.use_normalize_vert_groups and obj.type == "MESH" and obj.vertex_groups:
                bpy.context.scene.objects.active = obj
                obj.select = True
                bpy.ops.object.mode_set(mode="WEIGHT_PAINT")
                bpy.ops.object.vertex_group_normalize_all()
                bpy.ops.object.mode_set(mode="OBJECT")
                print("Normalized vertex groups for {}.".format(obj.name))
                obj.select = False

        # Merging
        if merging_enabled:
            print("Merging meshes.")
            if len(context.scene.llexportmerge.armatures) > 0:
                modifyObjects = self.merge_armatures(context, modifyObjects)
            if len(context.scene.llexportmerge.meshes) > 0:
                modifyObjects = self.merge_meshes(context, modifyObjects)

        keywords = self.as_keywords(ignore=("axis_forward",
                                            "axis_up",
                                            "global_scale",
                                            "check_existing",
                                            "filter_glob",
                                            "xna_validate",
                                            "filepath"
                                            ))

        exported_pathways = []

        single_mode = self.batch_mode == False

        if self.batch_mode:
            if self.use_anim:
                if self.anim_export_all_separate:
                    print("[DOS2DE-Exporter] Exporting all actions as separate animation files.")
                    
                    armature = next(iter(list(filter(lambda obj: obj.type == "ARMATURE", modifyObjects))), None)
                    if armature is not None:
                        start_progress(len(bpy.data.actions), "Exporting animations to DAE... {}/{}")

                        for action in bpy.data.actions:
                            export_name = "{}_Anim_{}".format(armature.name, action.name)
                            if self.auto_name == "ACTION":
                                export_name = action.name
                            
                            export_filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, export_name), self.filename_ext)
                            print("[DOS2DE-Exporter] Setting action to '{}' and exporting as '{}'.".format(action.name, export_filepath))
                            if armature.animation_data is None:
                                armature.animation_data_create()
                            armature.animation_data.action = action
                            if export_dae.save(self, context, [armature], filepath=export_filepath, **keywords) == {"FINISHED"}:
                                exported_pathways.append(export_filepath)
                            else:
                                self.report({"WARNING"}, "[DOS2DE-Exporter] Failed to export '{}'.".format(export_filepath))

                            update_progress(1)
                    result = {"FINISHED"}
                    finish_progress("All files exported.")
                else:
                    single_mode = True
            else:
                if self.use_active_layers:
                    progress_total = len((i for i in range(20) if context.scene.layers[i]))
                    start_progress(progress_total, "Exporting layers to DAE... {}/{}")
                    for i in range(20):
                        if context.scene.layers[i]:
                            export_list = list(filter(lambda obj: obj.layers[i], modifyObjects))
                            export_name = "{}_Layer{}".format(bpy.path.basename(bpy.context.blend_data.filepath), i)

                            if self.auto_name == "LAYER" and "namedlayers" in bpy.data.scenes[context.scene.name]:
                                namedlayers = getattr(bpy.data.scenes[context.scene.name], "namedlayers", None)
                                if namedlayers is not None:
                                    export_name = namedlayers.layers[i].name
                            
                            export_filepath = bpy.path.ensure_ext("{}\\{}".format(self.directory, export_name), self.filename_ext)
                            print("[DOS2DE-Exporter] Batch exporting layer '{}' as '{}'.".format(i, export_filepath))

                            if export_dae.save(self, context, export_list, filepath=export_filepath, **keywords) == {"FINISHED"}:
                                exported_pathways.append(export_filepath)
                            else:
                                self.report({"WARNING"}, "[DOS2DE-Exporter] Failed to export '{}'.".format(export_filepath))

                            update_progress(1)
                    
                    finish_progress("All files exported.")
                else:
                    single_mode = True
        if single_mode:
            pathNoextension = os.path.splitext(self.filepath)[0]
            export_filepath = bpy.path.ensure_ext(pathNoextension, self.filename_ext)
            result = export_dae.save(self, context, modifyObjects, filepath=export_filepath, **keywords)
            if result == {"FINISHED"}:
                exported_pathways.append(export_filepath)

        bpy.ops.object.select_all(action='DESELECT')

        for obj in copies:
            if obj is not None:
                obj.select = True

        bpy.ops.object.delete(use_global=True)

        #Cleanup
        for block in bpy.data.meshes:
            if block.users == 0:
                bpy.data.meshes.remove(block)

        for block in bpy.data.armatures:
            if block.users == 0:
                bpy.data.armatures.remove(block)

        for block in bpy.data.materials:
            if block.users == 0:
                bpy.data.materials.remove(block)

        for block in bpy.data.textures:
            if block.users == 0:
                bpy.data.textures.remove(block)

        for block in bpy.data.images:
            if block.users == 0:
                bpy.data.images.remove(block)

        bpy.ops.object.select_all(action='DESELECT')
        
        for obj in selectedObjects:
            obj.select = True
        
        if activeObject is not None:
            bpy.context.scene.objects.active = activeObject
        
        # Return to previous mode
        try:
            if current_mode is not None and activeObject is not None:
                if activeObject.type != "ARMATURE" and current_mode == "POSE":
                    bpy.ops.object.mode_set(mode="OBJECT")
                else:
                    bpy.ops.object.mode_set (mode=current_mode)
        except Exception as e:
            print("[DOS2DE-Collada] Error setting viewport mode:\n{}".format(e))

        if self.convert_gr2:
            if (addon_prefs.lslib_path is not None and addon_prefs.lslib_path != "" 
                and os.path.isfile(addon_prefs.lslib_path)):
                    start_progress(len(exported_pathways), "Exporting files to GR2... {}/{}")

                    for collada_file in exported_pathways:
                        gr2_path = str.replace(collada_file, ".dae", ".gr2")

                        gr2_options_str = self.build_gr2_options()

                        divine_exe = '"{}"'.format(addon_prefs.lslib_path)

                        proccess_args = "{} --loglevel all -g {} -s {} -d {} -i dae -o gr2 -a convert-model {}".format(
                            divine_exe, self.divine_settings.game, '"{}"'.format(collada_file), '"{}"'.format(gr2_path), gr2_options_str
                        )
                        
                        print("[DOS2DE-Collada] Starting GR2 conversion using divine.exe.")
                        print("[DOS2DE-Collada] Sending command: {}".format(proccess_args))

                        process = subprocess.run(proccess_args, 
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)

                        print(process.stdout)
                        
                        if process.returncode != 0:
                            #raise Exception("Error converting DAE to GR2: \"{}\"{}".format(process.stderr, process.stdout))
                            error_message = "[DOS2DE-Collada] [ERROR:{}] Error converting DAE to GR2. {}".format(process.returncode, '\n'.join(process.stdout.splitlines()[-1:]))
                            self.report({"ERROR"}, error_message)
                            print(error_message)
                        else:
                            if self.divine_settings.delete_collada and os.path.isfile(collada_file):
                                print("[DOS2DE-Collada] GR2 conversion successful. Deleting temporary collada file '{}'.".format(collada_file))
                                os.remove(collada_file)

                        update_progress(1)
                    
                    finish_progress("All files exported.")
            else:
                raise Exception("[DOS2DE-Collada] LSLib not found. Cannot convert to GR2.")
        
        #bpy.types.FILEBROWSER_HT_header.remove(draw_file_progress)

        return result

class DOS2DEExtraFlagsOperator(Operator):
    """Set the GR2 Extra Flag for Export"""
    bl_idname = "export_scene.dos2de_extraflagsop"
    bl_label = "DOS2DE Extra Flags"

    flag = EnumProperty(
        name="Flag",
        description="Set the custom export flag for this mesh.",
        items=gr2_extra_flags,
        default=("DISABLED")
    )

    def execute(self, context):
        obj = context.object
        if self.flag == "RIGID":
            obj["rigid"] = True
            if "cloth" in obj:
                del obj["cloth"]
            if "meshproxy" in obj:
                del obj["meshproxy"]
            if "rigidcloth" in obj:
                del obj["rigidcloth"]
        elif self.flag == "CLOTH":
            obj["cloth"] = True
            if "rigid" in obj:
                del obj["rigid"]
            if "meshproxy" in obj:
                del obj["meshproxy"]
            if "rigidcloth" in obj:
                del obj["rigidcloth"]
        elif self.flag == "MESHPROXY":
            obj["meshproxy"] = True
            if "rigid" in obj:
                del obj["rigid"]
            if "cloth" in obj:
                del obj["cloth"]
            if "rigidcloth" in obj:
                del obj["rigidcloth"]
        elif self.flag == "RIGIDCLOTH":
            obj["rigidcloth"] = True
            if "rigid" in obj:
                del obj["rigid"]
            if "cloth" in obj:
                del obj["cloth"]
            if "meshproxy" in obj:
                del obj["meshproxy"]
        else:
            if "rigid" in obj:
                del obj["rigid"]
            if "cloth" in obj:
                del obj["cloth"]
            if "meshproxy" in obj:
                del obj["meshproxy"]
            if "rigidcloth" in obj:
                del obj["rigidcloth"]
        return {'FINISHED'}

    def invoke(self, context, event):
        if "rigid" in context.object:
            self.flag = "RIGID"
        elif "cloth" in context.object:
            self.flag = "CLOTH"
        elif "meshproxy" in context.object:
            self.flag = "MESHPROXY"
        elif "rigidcloth" in context.object:
            self.flag = "RIGIDCLOTH"
        
        wm = context.window_manager
        return wm.invoke_props_dialog(self)
    
    def draw(self, context):
        self.layout.prop(self, "flag")

def menu_func(self, context):
    self.layout.operator(ExportDAE.bl_idname, text="DOS2DE Collada (.dae, .gr2)")

addon_keymaps = []

def draw_export_options(self, context):
    col = self.layout.column()
    col.label("DOS2DE Collada Settings")
    col.operator(DOS2DEExtraFlagsOperator.bl_idname)

added_export_options = False

@persistent
def leaderhelpers_register_exportdraw(scene):
    if hasattr(scene, "llexport_object_drawhandler"):
        global added_export_options
        if added_export_options is False:
            try:
                funclist = getattr(scene, "llexport_object_drawhandler", None)
                if funclist is not None:
                    funclist.add(draw_export_options)
            except Exception as e:
                print("[DivinityColladaExporter:leaderhelpers_register_exportdraw] Error adding draw function to list:\nError:\n{}".format(e))
            bpy.app.handlers.scene_update_post.remove(leaderhelpers_register_exportdraw)
            added_export_options = True

def register():
    bpy.utils.register_module(__name__)
    #bpy.utils.register_class(ExportDAE)
    bpy.types.INFO_MT_file_export.append(menu_func)

    """ bpy.types.Scene.daefileprogress = PointerProperty(
        name="File Export Progress",
        description="Used to render file browser progress",
        type=ExportProgressProperties
    ) """

    wm = bpy.context.window_manager
    km = wm.keyconfigs.addon.keymaps.new('Window', space_type='EMPTY', region_type='WINDOW', modal=False)

    kmi = km.keymap_items.new(ExportDAE.bl_idname, 'E', 'PRESS', ctrl=True, shift=True)
    #print(__name__)
    #kmi.properties.name = ExportDAE.bl_idname
    addon_keymaps.append((km, kmi))
    
    bpy.app.handlers.scene_update_post.append(leaderhelpers_register_exportdraw)

def unregister():
    bpy.utils.unregister_module(__name__)
    #bpy.utils.unregister_class(ExportDAE)

    try:
        bpy.types.INFO_MT_file_export.remove(menu_func)
        bpy.app.handlers.scene_update_post.remove(leaderhelpers_register_exportdraw)
        #bpy.types.FILEBROWSER_HT_header.remove(draw_file_progress)
        #del bpy.types.Scene.daefileprogress

        wm = bpy.context.window_manager
        kc = wm.keyconfigs.addon
        if kc:
            for km, kmi in addon_keymaps:
                km.keymap_items.remove(kmi)
        addon_keymaps.clear()
    except:
        pass

if __name__ == "__main__":
    register()

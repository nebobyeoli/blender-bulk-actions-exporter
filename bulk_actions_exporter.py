bl_info = {
    "name": "Bulk Actions Exporter (FBX)",
    "author": "sivert-io (orig), nebobyeoli (fork)",
    "version": (2, 3, 7),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > Actions Exporter", # actual sidebar is set via bl_category in each class
    "description": "Bulk Actions exporter in FBX format for Blender 4.0+, with additional QOL options",
    "doc_url": "https://github.com/nebobyeoli/blender-bulk-actions-exporter", # "Website"
    "tracker_url": "", # "Feedback - Report a Bug"
    "category": "Import-Export",
}

# nebobyeoli(fork): The additional QOL options are mostly written with google ai search mode for personal use on Blender 4.5 LTS, Windows 10

import bpy
import os
import ast # used in class FBX_OT_load_native_preset(Operator)
import re # used for regex naming
import fnmatch # used for Action Filter List: + Exclusion Filter

from bpy.types import Operator, Panel, PropertyGroup, Menu
from bpy.props import *


### Action Filter List - STEP 1: Add the Checklist Property Groups
class FBXActionSelectionItem(PropertyGroup):
    """Holds the export toggle state for an individual action"""
    is_selected: BoolProperty(name="", default=True)
    action_name: StringProperty(name="")

# Add this update function to sync your project data dynamically when you open the UI panel
# def update_action_filter_list(self, context):
#     p = context.scene.fbx_export
#     # Clear out items that no longer exist in the Blender project database
#     existing_names = {a.name for a in bpy.data.actions if a.use_fake_user}
#    
#     # Remove dead entries
#     for i in reversed(range(len(p.action_filter_items))):
#         if p.action_filter_items[i].action_name not in existing_names:
#             p.action_filter_items.remove(i)
#            
#     # Add newly discovered actions to the filter checklist layout structure
#     current_items = {item.action_name for item in p.action_filter_items}
#     for action in bpy.data.actions:
#         if action.use_fake_user and action.name not in current_items:
#             item = p.action_filter_items.add()
#             item.action_name = action.name
#             item.is_selected = True

def sync_action_filter_list(scene):
    """Safely synchronizes action items without crashing the UI draw loop"""
    p = scene.fbx_export
    existing_names = {a.name for a in bpy.data.actions if a.use_fake_user}
    
    # Remove old items
    for i in reversed(range(len(p.action_filter_items))):
        if p.action_filter_items[i].action_name not in existing_names:
            p.action_filter_items.remove(i)
            
    # Add new items safely
    current_items = {item.action_name for item in p.action_filter_items}
    for action in bpy.data.actions:
        if action.use_fake_user and action.name not in current_items:
            item = p.action_filter_items.add()
            item.action_name = action.name
            item.is_selected = True

def trigger_list_update(self, context):
    """Callback function triggered when settings change"""
    sync_action_filter_list(context.scene)
### end of STEP 1


class FBXExportSettings(PropertyGroup):
    export_path: StringProperty(
        name="Export Path",
        description="Path to export files (supports '//' for relative paths)",
        default="//"
    )

    # Transform
    global_scale: FloatProperty(name="Scale", default=1.0, min=0.001, max=1000.0)
    apply_scale_options: EnumProperty(
        name="Apply Scalings",
        items=[
            ('FBX_SCALE_NONE', "All Local", ""),
            ('FBX_SCALE_UNITS', "FBX Units Scale", ""),
            ('FBX_SCALE_CUSTOM', "FBX Custom Scale", ""),
            ('FBX_SCALE_ALL', "FBX All", "")
        ],
        default='FBX_SCALE_NONE'
    )
    axis_forward: EnumProperty(
        name="Forward",
        items=[(x, x, "") for x in ['X', 'Y', 'Z', '-X', '-Y', '-Z']],
        default='-Z'
    )
    axis_up: EnumProperty(
        name="Up",
        items=[(x, x, "") for x in ['X', 'Y', 'Z', '-X', '-Y', '-Z']],
        default='Y'
    )
    apply_unit_scale: BoolProperty(name="Apply Unit")
    use_space_transform: BoolProperty(name="Use Space Transform", default=True)
    bake_space_transform: BoolProperty(name="Apply Transform")

    # Geometry
    mesh_smooth_type: EnumProperty(
        name="Smoothing",
        items=[('OFF', "Normals Only", ""), ('FACE', "Face", ""), ('EDGE', "Edge", "")],
        default='OFF'
    )
    use_subsurf: BoolProperty(name="Export Subdivision Surface")
    use_mesh_modifiers: BoolProperty(name="Apply Modifiers", default=True)
    use_mesh_edges: BoolProperty(name="Loose Edges")
    use_triangles: BoolProperty(name="Triangulate Faces")
    use_tspace: BoolProperty(name="Tangent Space")
    colors_type: EnumProperty(
        name="Vertex Colors",
        items=[('NONE', "None", ""), ('SRGB', "sRGB", ""), ('LINEAR', "Linear", "")],
        default='SRGB'
    )
    prioritize_active_color: BoolProperty(name="Prioritize Active Color")

    # Armature
    use_armature_deform_only: BoolProperty(name="Only Deform Bones")
    add_leaf_bones: BoolProperty(name="Add Leaf Bones", default=True)
    armature_nodetype: EnumProperty(
        name="Armature FBXNode Type",
        items=[('NULL', "Null", ""), ('ROOT', "Root", ""), ('LIMBNODE', "LimbNode", "")],
        default='NULL'
    )
    primary_bone_axis: EnumProperty(
        name="Primary Bone Axis",
        items=[(x, x, "") for x in ['X', 'Y', 'Z', '-X', '-Y', '-Z']],
        default='Y'
    )
    secondary_bone_axis: EnumProperty(
        name="Secondary Bone Axis",
        items=[(x, x, "") for x in ['X', 'Y', 'Z', '-X', '-Y', '-Z']],
        default='X'
    )

    ## Options addition - STEP 1: Update the Properties
    use_selection: BoolProperty(name="Selected Objects", default=False)
    use_visible: BoolProperty(name="Visible Objects", default=True)
    use_active_collection: BoolProperty(name="Active Collection", default=False)
    object_types: EnumProperty(
        name="Object Types",
        options={'ENUM_FLAG'},
        items=[
            ('EMPTY', "Empty", ""),
            ('CAMERA', "Camera", ""),
            ('LIGHT', "Lamp", ""),
            ('ARMATURE', "Armature", ""),
            ('MESH', "Mesh", ""),
            ('OTHER', "Other", "")
        ],
        default={'ARMATURE', 'MESH', 'OTHER'}
    )
    use_custom_props: BoolProperty(name="Custom Properties", default=False)

    # Animation
    # use_animation: BoolProperty(name="Bake Animation", default=True) # UI option, but fix it to true instead bc this is an ACTIONS exporter, an exporter for anims
    use_animation = True # fixed value, no user option
    bake_anim_use_all_bones: BoolProperty(name="Key All Bones", default=True)
    bake_anim_use_nla_strips: BoolProperty(name="NLA Strips", default=False)
    # bake_anim_use_all_actions: BoolProperty(name="All Actions", default=False) # UI option, but unneeded bc we'll use "Select Actions to Export" instead
    bake_anim_use_all_actions = False # fixed value, no user option
    bake_anim_force_startend_keying: BoolProperty(name="Force Start/End Keying", default=False)
    bake_anim_step: FloatProperty(name="Sampling Rate", default=1.0, min=0.01, max=100.0)
    bake_anim_simplify_factor: FloatProperty(name="Simplify", default=0.00, min=0.0, max=10.0)
    ## end of STEP 1

    # File Naming
    name_prefix: StringProperty(name="Add Prefix", default="")
    name_postfix: StringProperty(name="Add Postfix", default="")
    remove_prefix: StringProperty(name="Remove Prefix", default="", description="Removes this specific string from the start of the action name")
    remove_postfix: StringProperty(name="Remove Postfix", default="", description="Removes this specific string from the end of the action name")

    # Regex Naming
    use_regex: BoolProperty(
        name="Use Regular Expressions", 
        default=False, 
        description="Enable advanced Python regex find and replace over action names"
    )
    regex_find: StringProperty(
        name="Find Pattern", 
        default="", 
        description="The regex search pattern (e.g., ^prefix_.*|.*_postfix$)"
    )
    regex_replace: StringProperty(
        name="Replace With", 
        default="", 
        description="The replacement text (supports groups like \\1)"
    )


    ### Action Filter List - STEP 2: Update the Global Settings Class
    action_filter_items: CollectionProperty(type=FBXActionSelectionItem)
    action_filter_search: StringProperty(
        name="Search Actions", 
        default="", 
        description="Filter down the action checklist view by text pattern matching",
        update=trigger_list_update # Triggers sync safely outside draw loops
    )
    ### end of STEP 2
    
    # + Exclusion Filter
    use_exclusion_filter: BoolProperty(
        name="Skip by Naming Pattern",
        default=False,
        description="Automatically skip exporting any actions that match an exclusion text pattern"
    )
    exclusion_pattern: StringProperty(
        name="Pattern",
        default="test_*",
        description="The wildcard pattern to skip (e.g., test_*, *_backup, temp_?)"
    )

    # + Inclusion Filter
    use_inclusion_filter: BoolProperty(
        name="Limit by Naming Pattern",
        default=False,
        description="Only export actions that match an explicit text pattern string"
    )
    inclusion_pattern: StringProperty(
        name="Pattern",
        default="anim_*",
        description="The wildcard pattern to include exclusively (e.g., anim_*, *_v1)"
    )




# ─── NATIVE FBX PRESET COMPATIBILITY SYSTEM ──────────────────────────────────

class FBX_OT_load_native_preset(Operator):
    """Internal operator to parse and map native FBX export preset files safely"""
    bl_idname = "fbx_export.load_native_preset"
    bl_label = "Load Native Preset"
    bl_options = {'INTERNAL'}
    
    filepath: StringProperty()

    def execute(self, context):
        if not os.path.exists(self.filepath):
            self.report({'ERROR'}, "Preset file not found")
            return {'CANCELLED'}
            
        p = context.scene.fbx_export
        
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Look only for lines modifying properties on the operator proxy (op.)
                    if line.startswith("op.") and "=" in line:
                        # Split into property name and raw python value string
                        prop_part, value_part = line.split("=", 1)
                        prop_name = prop_part.replace("op.", "").strip()
                        value_str = value_part.strip()
                        
                        # Evaluate Python literal values safely (strings, floats, bools, etc.)
                        try:
                            value = ast.literal_eval(value_str)
                        except Exception:
                            continue # Skip non-literal expressions or comments
                        

                        # # Map native names directly to your PropertyGroup attributes
                        # if hasattr(p, prop_name):
                        #     # Convert lists from preset files into a Python set for ENUM_FLAG fields
                        #     if prop_name == "object_types" and isinstance(value, (list, tuple, set)):
                        #         setattr(p, prop_name, set(value))
                        #     else:
                        #         setattr(p, prop_name, value)

                        # Map native names directly to your PropertyGroup attributes
                        if hasattr(p, prop_name):
                            setattr(p, prop_name, value)
                        elif prop_name == "mesh_smooth_type":
                            setattr(p, "mesh_smooth_type", value)

            preset_title = os.path.splitext(os.path.basename(self.filepath))[0]
            self.report({'INFO'}, f"Preset loaded: {preset_title}")
            
        except Exception as e:
            self.report({'WARNING'}, f"Failed to parse preset: {e}")
            
        return {'FINISHED'}

class FBX_MT_native_export_presets(Menu):
    """Dynamic menu listing all built-in and user-created presets for export_scene.fbx"""
    bl_label = "Native FBX Presets"
    bl_idname = "FBX_MT_native_export_presets"

    def draw(self, context):
        layout = self.layout
        
        # Automatically discover active system and user directory presets for native FBX exports
        preset_paths = bpy.utils.preset_paths("operator/export_scene.fbx")
        
        found_presets = False
        for path in preset_paths:
            if not os.path.exists(path):
                continue
            for f in sorted(os.listdir(path)):
                if f.endswith(".py"):
                    found_presets = True
                    # Clean up file name formatting for readable menu item text
                    preset_name = os.path.splitext(f)[0].replace("_", " ")
                    full_path = os.path.join(path, f)
                    
                    props = layout.operator("fbx_export.load_native_preset", text=preset_name)
                    props.filepath = full_path
                    
        if not found_presets:
            layout.label(text="No Saved FBX Presets Found")

class FBX_PT_export_presets_panel(Panel):
    bl_label = "Operator Presets"
    bl_idname = "FBX_PT_export_presets_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"
    bl_parent_id = "FBX_PT_export_main"

    def draw(self, context):
        layout = self.layout
        row = layout.row(align=True)
        # Dropdown container referencing our native scanner layout menu
        row.menu("FBX_MT_native_export_presets", text="FBX Native Presets")

# ──────────────────────────────────────────────────────────────────────────

class FBX_PT_export_main(Panel):
    bl_label = "Bulk Actions Exporter (FBX)"
    bl_idname = "FBX_PT_export_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"

    def draw(self, context):
        pass

class FBX_PT_path(Panel):
    bl_label = "Export Path"
    bl_parent_id = "FBX_PT_export_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene.fbx_export, "export_path")

        layout.label(text="If unspecified, defaults to '//' (directory of this .blend file).", icon='INFO')




def get_predicted_export_name(action_name, p):
    """Processes an action name based on the addon naming/regex settings."""
    export_name = action_name
    
    if p.use_regex:
        if p.regex_find:
            try:
                export_name = re.sub(p.regex_find, p.regex_replace, export_name)
            except Exception:
                pass  # Ignore invalid regex patterns during live typing
    else:
        if p.remove_prefix and export_name.startswith(p.remove_prefix):
            export_name = export_name[len(p.remove_prefix):]
            
        if p.remove_postfix and export_name.endswith(p.remove_postfix):
            export_name = export_name[:-len(p.remove_postfix)]
            
        export_name = f"{p.name_prefix}{export_name}{p.name_postfix}"
        
    # Auto-validation: Strip illegal Windows/Unix path characters (/, \, ?, *, :, ", <, >, |)
    illegal_chars = ['/', '\\', '?', '*', ':', '"', '<', '>', '|']
    for char in illegal_chars:
        export_name = export_name.replace(char, "")
        
    # Fallback to a default name if the string ends up completely empty
    if not export_name.strip():
        export_name = "unnamed_action"
        
    return export_name


class FBX_PT_naming(Panel):
    bl_label = "File Naming"
    bl_parent_id = "FBX_PT_export_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"
    bl_options = {'DEFAULT_CLOSED'}

    ## (replace only, no regex)
    # def draw(self, context):
    #     p = context.scene.fbx_export
    #     layout = self.layout
    #    
    #     col = layout.column(align=True)
    #     col.label(text="Add Modifiers:")
    #     col.prop(p, "name_prefix")
    #     col.prop(p, "name_postfix")
    #    
    #     col_remove = layout.column(align=True)
    #     col_remove.label(text="Remove Patterns:")
    #     col_remove.prop(p, "remove_prefix")
    #     col_remove.prop(p, "remove_postfix")

    ## (with regex option)
    def draw(self, context):
        p = context.scene.fbx_export
        layout = self.layout
        
        # Add the Regex toggle switch at the top of the panel
        layout.prop(p, "use_regex", toggle=True, icon='TEXT')
        layout.separator()
        
        if p.use_regex:
            col = layout.column(align=True)
            col.label(text="Regex Find & Replace:")
            col.prop(p, "regex_find", text="Find")
            col.prop(p, "regex_replace", text="Replace")
            
            # Tiny helper hint for the user
            col.separator()
            col.label(text="Find '^anim_' to strip prefixes.", icon='INFO')
            col.label(text="Find 'v[0-9]+' to strip versions.", icon='INFO')
            col.label(text="Find: 'char_(.*)_walk_(.*)', Replace: '\\1_walk_\\2' to dynamically replace any.", icon='INFO')
        else:
            col = layout.column(align=True)
            col.label(text="Add Modifiers:")
            col.prop(p, "name_prefix")
            col.prop(p, "name_postfix")
            
            col_remove = layout.column(align=True)
            col_remove.label(text="Remove Patterns:")
            col_remove.prop(p, "remove_prefix")
            col_remove.prop(p, "remove_postfix")


        # ─── Live Preview Element ───
        layout.separator()
        obj = context.object
        active_action = obj.animation_data.action if (obj and obj.animation_data) else None
        
        box = layout.box()
        box.label(text="Live Naming Preview:", icon='FILE_TICK')
        if active_action:
            preview_name = get_predicted_export_name(active_action.name, p)
            box.label(text=f"Original: {active_action.name}", icon='DOT')
            box.label(text=f"Export:   {preview_name}.fbx", icon='CHECKMARK')
        else:
            box.label(text="No active action found on selected object.", icon='ERROR')


### Action Filter List - STEP 3: Add the Action Filter UI Panel
class FBX_OT_refresh_actions(Operator):
    """Scan the blend file for new or updated actions safely"""
    bl_idname = "fbx_export.refresh_actions"
    bl_label = "Refresh Action List"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        sync_action_filter_list(context.scene)
        return {'FINISHED'}

class FBX_PT_action_selector(Panel):
    bl_label = "Select Actions to Export"
    bl_parent_id = "FBX_PT_export_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"

    def draw(self, context):
        p = context.scene.fbx_export
        layout = self.layout
        layout.label(text="Actions need to have 'Fake User' enabled to be detected.", icon='INFO')

        # update_action_filter_list(None, context) # Keep the checklist data layout fully synchronized with current project actions
        # Safe drawing layout instead: Fix error from (None, context)
        row_top = layout.row(align=True)
        row_top.operator("fbx_export.refresh_actions", text="Scan Actions", icon='FILE_REFRESH')
        
        # Draw Master Select All / Deselect All convenience control tools
        row_tools = layout.row(align=True)
        op_all = row_tools.operator("fbx_export.action_select_all", text="Select All")
        op_all.action_type = 'SELECT'
        op_none = row_tools.operator("fbx_export.action_select_all", text="Deselect All")
        op_none.action_type = 'DESELECT'
        
        layout.prop(p, "action_filter_search", icon='VIEWZOOM', text="")

        
        # Action Filter List - ─── + Inclusion & Exclusion Filter UI Block ───
        layout.separator()
        box_filters = layout.box()
        box_filters.label(text="Export Filters:", icon='FILTER')

        # # Action Filter List - ─── + Exclusion Filter UI ───
        # layout.separator()
        # box_ex = layout.box()
        # box_ex.prop(p, "use_exclusion_filter", text="Auto-Skip Patterns", icon='FILTER')
        # if p.use_exclusion_filter:
        #     col_ex = box_ex.column(align=True)
        #     col_ex.prop(p, "exclusion_pattern", text="Match")
        #     col_ex.label(text="Use '*' for wildcards (e.g. test_*, *_backup)", icon='INFO')

        # + Inclusion Filter UI
        row_inc = box_filters.row()
        row_inc.prop(p, "use_inclusion_filter", text="Include Only")
        if p.use_inclusion_filter:
            box_filters.prop(p, "inclusion_pattern", text="Match")
            
        # + Exclusion Filter UI
        row_exc = box_filters.row()
        row_exc.prop(p, "use_exclusion_filter", text="Exclude")
        if p.use_exclusion_filter:
            box_filters.prop(p, "exclusion_pattern", text="Match")
        
        
        # Render the scrollable checklist box item selection view container 
        layout.separator()
        box = layout.box()
        col = box.column(align=True)
        
        search_query = p.action_filter_search.lower()
        visible_items = 0
        total_queued = 0
        
        for item in p.action_filter_items:
            # Handle text search bar filter reduction
            if search_query and search_query not in item.action_name.lower():
                continue
            
            
            # Determine wildcard pattern states for live styling previews
            is_pattern_skipped = False
            
            # Run background Inclusion Filter evaluation
            if p.use_inclusion_filter and p.inclusion_pattern:
                if not fnmatch.fnmatch(item.action_name.lower(), p.inclusion_pattern.lower()):
                    is_pattern_skipped = True
            # Run background Exclusion Filter evaluation
            if p.use_exclusion_filter and p.exclusion_pattern:
                if fnmatch.fnmatch(item.action_name.lower(), p.exclusion_pattern.lower()):
                    is_pattern_skipped = True


            # row = col.row()
            # row.prop(item, "is_selected", text="")
            # row.label(text=item.action_name, icon='ANIM')
            # visible_items += 1
            
            row = col.row()
            # Filter visualization Rule: Gray out items that fail Inclusion/Exclusion Filters
            if is_pattern_skipped:
                row.active = False # Grays out the row controls
                row.prop(item, "is_selected", text="")
                row.label(text=f"{item.action_name} (Filtered Out)", icon='CANCEL')
            else:
                row.prop(item, "is_selected", text="")
                row.label(text=item.action_name, icon='ANIM')
                if item.is_selected:
                    total_queued += 1
            visible_items += 1
            

        # Display Dynamic Readout Queue Summary Counters
        layout.separator()
        if visible_items == 0:
            col.label(text="No matching actions found.", icon='INFO')
            col.label(text="Click 'Scan Actions', or check Export Filters.", icon='INFO')
        else:
            layout.label(text=f"Ready to Export: {total_queued} actions queued", icon='FILE_TICK')
### end of STEP 3

### Action Filter List - STEP 4: Add the Helper Section Operators
class FBX_OT_action_select_all(Operator):
    """Select or deselect all items matching active action checklist configurations"""
    bl_idname = "fbx_export.action_select_all"
    bl_label = "Bulk Select Actions"
    bl_options = {'INTERNAL'}
    
    action_type: EnumProperty(items=[('SELECT', "", ""), ('DESELECT', "", "")])

    def execute(self, context):
        p = context.scene.fbx_export
        search_query = p.action_filter_search.lower()
        
        for item in p.action_filter_items:
            if search_query and search_query not in item.action_name.lower():
                continue
            item.is_selected = (self.action_type == 'SELECT')
            
        return {'FINISHED'}
### end of STEP 4



class FBX_PT_transform(Panel):
    bl_label = "Transform"
    bl_parent_id = "FBX_PT_export_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        p = context.scene.fbx_export
        layout = self.layout
        layout.prop(p, "global_scale")
        layout.prop(p, "apply_scale_options")
        layout.prop(p, "axis_forward")
        layout.prop(p, "axis_up")
        layout.prop(p, "apply_unit_scale")
        layout.prop(p, "use_space_transform")
        layout.prop(p, "bake_space_transform")

class FBX_PT_geometry(Panel):
    bl_label = "Geometry"
    bl_parent_id = "FBX_PT_export_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        p = context.scene.fbx_export
        layout = self.layout
        layout.prop(p, "mesh_smooth_type")
        layout.prop(p, "use_subsurf")
        layout.prop(p, "use_mesh_modifiers")
        layout.prop(p, "use_mesh_edges")
        layout.prop(p, "use_triangles")
        layout.prop(p, "use_tspace")
        layout.prop(p, "colors_type")
        layout.prop(p, "prioritize_active_color")

class FBX_PT_armature(Panel):
    bl_label = "Armature"
    bl_parent_id = "FBX_PT_export_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        p = context.scene.fbx_export
        layout = self.layout
        layout.prop(p, "primary_bone_axis")
        layout.prop(p, "secondary_bone_axis")
        layout.prop(p, "armature_nodetype")
        layout.prop(p, "use_armature_deform_only")
        layout.prop(p, "add_leaf_bones")

## Options addition - STEP 2: Add the UI Panels
class FBX_PT_include(Panel):
    bl_label = "Include"
    bl_parent_id = "FBX_PT_export_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        p = context.scene.fbx_export
        layout = self.layout
        
        col = layout.column(heading="Limit to")
        col.prop(p, "use_selection")
        col.prop(p, "use_visible")
        col.prop(p, "use_active_collection")
        
        layout.prop(p, "object_types")
        layout.prop(p, "use_custom_props")

class FBX_PT_animation(Panel):
    bl_label = "Animation"
    bl_parent_id = "FBX_PT_export_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"
    bl_options = {'DEFAULT_CLOSED'}

    def draw_header(self, context):
        p = context.scene.fbx_export
        self.layout.prop(p, "use_animation", text="")

    def draw(self, context):
        p = context.scene.fbx_export
        layout = self.layout
        layout.active = p.use_animation
        
        layout.prop(p, "bake_anim_use_all_bones")
        layout.prop(p, "bake_anim_use_nla_strips")
        layout.prop(p, "bake_anim_use_all_actions")
        layout.prop(p, "bake_anim_force_startend_keying")
        layout.prop(p, "bake_anim_step")
        layout.prop(p, "bake_anim_simplify_factor")
## end of STEP 2


class FBX_PT_export_button(Panel):
    bl_label = "Export"
    bl_parent_id = "FBX_PT_export_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Actions Exporter"

    def draw(self, context):
        layout = self.layout
        layout.operator("export_fbx.actions", text="Export All Actions")

class ExportAllActionsOperator(Operator):
    bl_idname = "export_fbx.actions"
    bl_label = "Export All Actions"

    def execute(self, context):
        obj = context.object
        p = context.scene.fbx_export

        if not obj or obj.type != 'ARMATURE':
            self.report({'ERROR'}, "Select an Armature")
            return {'CANCELLED'}
        


        ### Edit "Export Path"

        # if not p.export_path:
        #     self.report({'ERROR'}, "Set an export directory")
        #     return {'CANCELLED'}

        # Use current .blend file's path if unspecified
        if not p.export_path:
            p.export_path = "//"
        
        export_path = p.export_path
        if p.export_path.startswith("//"):
            export_path = bpy.path.abspath(p.export_path) # os.path.dirname(bpy.data.filepath)
        # # If the user picked an absolute path, convert it to Blender relative '//'
        # if path and not path.startswith("//"):
        #     abs_path = os.path.abspath(bpy.path.abspath(path))
        #     rel_path = bpy.path.relpath(abs_path)

        # Create folder if not exist
        os.makedirs(export_path, exist_ok=True)



        if not obj.animation_data:
            obj.animation_data_create()

        scene = context.scene
        old_start = scene.frame_start
        old_end = scene.frame_end
        exported = 0


        # Store the original active action to restore it later
        original_active_action = obj.animation_data.action


        ### Action Filter List - STEP 5: Update the Operator Filtering Logic
        # Create a fast lookup map dictionary of your checked custom UI choices
        selection_map = {item.action_name: item.is_selected for item in p.action_filter_items}

        for action in bpy.data.actions:
            if not action.use_fake_user:
                continue

            # STEP 5: Intercept checklist choice: Skip this action loop if deselected by the user
            # 1. Evaluate User Selection List Filter
            if action.name in selection_map and not selection_map[action.name]:
                continue

            # 2. (+ Inclusion Filter) Evaluate Naming Wildcard Pattern Exclusion Filter
            if p.use_inclusion_filter and p.inclusion_pattern:
                if not fnmatch.fnmatch(action.name.lower(), p.inclusion_pattern.lower()):
                    continue # Skip action

            # 2. (+ Exclusion Filter) Evaluate Naming Wildcard Pattern Exclusion Filter
            if p.use_exclusion_filter and p.exclusion_pattern:
                if fnmatch.fnmatch(action.name.lower(), p.exclusion_pattern.lower()): # Use lowercase to search case-insensitive and robust
                    continue
            ### end of STEP 5

            start = int(action.frame_range[0])
            end = int(action.frame_range[1])

            # 1. Force the active action database slot to target the current loop's action
            obj.animation_data.action = action

            # 2. Maintain NLA track setup if required for custom track properties
            track = obj.animation_data.nla_tracks.new()
            track.name = f"TEMP_{action.name}"
            strip = track.strips.new(action.name, start, action)
            strip.action_frame_start = start
            strip.action_frame_end = end
            
            scene.frame_start = start
            scene.frame_end = end
            
            
            # ## Process string removal and additions
            # # filepath = os.path.join(export_path, f"{action.name}.fbx")
            # export_name = action.name
            # 
            # if p.use_regex:
            #     # Process Regex renaming pipeline
            #     if p.regex_find:
            #         try:
            #             export_name = re.sub(p.regex_find, p.regex_replace, export_name)
            #         except Exception as re_err:
            #             self.report({'WARNING'}, f"Regex Error on {action.name}: {re_err}")
            #     final_filename = f"{export_name}.fbx"
            # 
            # else:
            #     # Process standard string removal and additions
            #     if p.remove_prefix and export_name.startswith(p.remove_prefix):
            #         export_name = export_name[len(p.remove_prefix):]
            #     if p.remove_postfix and export_name.endswith(p.remove_postfix):
            #         export_name = export_name[:-len(p.remove_postfix)]
            # 
            #     # Combine final filename with configured strings
            #     final_filename = f"{p.name_prefix}{export_name}{p.name_postfix}.fbx"
            # 
            # filepath = os.path.join(export_path, final_filename)

            # Use our unified sanitization and conversion helper function
            export_name = get_predicted_export_name(action.name, p)
            filepath = os.path.join(export_path, f"{export_name}.fbx")


            try:
                ## Options addition - STEP 3: Update the Operator Parameters
                bpy.ops.export_scene.fbx(
                    filepath=filepath,
                    use_selection=p.use_selection,
                    use_visible=p.use_visible,
                    use_active_collection=p.use_active_collection,
                    object_types=p.object_types,
                    use_custom_props=p.use_custom_props,

                    global_scale=p.global_scale,
                    apply_scale_options=p.apply_scale_options,
                    axis_forward=p.axis_forward,
                    axis_up=p.axis_up,
                    apply_unit_scale=p.apply_unit_scale,
                    use_space_transform=p.use_space_transform,
                    bake_space_transform=p.bake_space_transform,
                    mesh_smooth_type=p.mesh_smooth_type,
                    use_subsurf=p.use_subsurf,
                    use_mesh_modifiers=p.use_mesh_modifiers,
                    use_mesh_edges=p.use_mesh_edges,
                    use_triangles=p.use_triangles,
                    use_tspace=p.use_tspace,
                    colors_type=p.colors_type,
                    prioritize_active_color=p.prioritize_active_color,
                    # object_types=set(p.object_types),
                    use_armature_deform_only=p.use_armature_deform_only,
                    add_leaf_bones=p.add_leaf_bones,
                    armature_nodetype=p.armature_nodetype,
                    primary_bone_axis=p.primary_bone_axis,
                    secondary_bone_axis=p.secondary_bone_axis,
                    
                    bake_anim=p.use_animation,
                    bake_anim_use_all_bones=p.bake_anim_use_all_bones,
                    bake_anim_use_nla_strips=p.bake_anim_use_nla_strips,
                    bake_anim_use_all_actions=p.bake_anim_use_all_actions,
                    bake_anim_force_startend_keying=p.bake_anim_force_startend_keying,
                    bake_anim_step=p.bake_anim_step,
                    bake_anim_simplify_factor=p.bake_anim_simplify_factor
                )
                ## end of STEP 3

                exported += 1
            except Exception as e:
                self.report({'WARNING'}, f"Export failed: {action.name}: {e}")
        
            # Clean up the temporary NLA track
            obj.animation_data.nla_tracks.remove(track)
            
        # Restore the viewport state back to what the user originally had selected
        obj.animation_data.action = original_active_action


        scene.frame_start = old_start
        scene.frame_end = old_end
        self.report({'INFO'}, f"Exported {exported} actions")
        return {'FINISHED'}


## Options addition - STEP 4: Register the Panels (added to list: FBX_PT_include, FBX_PT_animation)
### Action Filter List - STEP 6: Update the Operator Filtering Logic  (added to list: FBXActionSelectionItem, FBX_OT_action_select_all, FBX_PT_action_selector)
classes = [
    FBXActionSelectionItem,
    FBXExportSettings,

    FBX_OT_load_native_preset,
    FBX_MT_native_export_presets,
    FBX_PT_export_main,
    FBX_PT_export_presets_panel,
    FBX_PT_path,

    FBX_PT_naming,

    FBX_PT_include,
    FBX_PT_transform,
    FBX_PT_geometry,
    FBX_PT_armature,
    FBX_PT_animation,

    FBX_OT_action_select_all,
    FBX_OT_refresh_actions,
    FBX_PT_action_selector,

    FBX_PT_export_button,
    ExportAllActionsOperator,
]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.fbx_export = PointerProperty(type=FBXExportSettings)

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.fbx_export

if __name__ == "__main__":
    register()

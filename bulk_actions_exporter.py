bl_info = {
    "name": "Bulk Actions Exporter (FBX)",
    "author": "sivert-io (orig), nebobyeoli (fork)",
    "version": (2, 3, 1),
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
from bpy.types import Operator, Panel, PropertyGroup, Menu
from bpy.props import *

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

    # Options addition STEP 1: Update the Properties
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
    bake_anim_use_all_actions: BoolProperty(name="All Actions", default=False)
    bake_anim_force_startend_keying: BoolProperty(name="Force Start/End Keying", default=False)
    bake_anim_step: FloatProperty(name="Sampling Rate", default=1.0, min=0.01, max=100.0)
    bake_anim_simplify_factor: FloatProperty(name="Simplify", default=0.00, min=0.0, max=10.0)
    # end of STEP 1


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
                        
                        # Map native names directly to your PropertyGroup attributes
                        if hasattr(p, prop_name):
                            # Convert lists from preset files into a Python set for ENUM_FLAG fields
                            if prop_name == "object_types" and isinstance(value, (list, tuple, set)):
                                setattr(p, prop_name, set(value))
                            else:
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

# Options addition STEP 2: Add the UI Panels
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
# end of STEP 2


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

        for action in bpy.data.actions:
            if not action.use_fake_user:
                continue

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
            filepath = os.path.join(export_path, f"{action.name}.fbx")

            try:
                # Options addition STEP 3: Update the Operator Parameters
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
                # end of STEP 3

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

# Options addition STEP 4: Register the Panels (added FBX_PT_include, FBX_PT_animation to the list)
classes = [
    FBXExportSettings,

    FBX_OT_load_native_preset,
    FBX_MT_native_export_presets,
    FBX_PT_export_main,
    FBX_PT_export_presets_panel,
    FBX_PT_path,

    FBX_PT_include,
    FBX_PT_transform,
    FBX_PT_geometry,
    FBX_PT_armature,
    FBX_PT_animation,

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

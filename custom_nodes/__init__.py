# This file makes Python treat the `custom_nodes` directory as a package.
# It can also be used to load nodes from subdirectories.

# If loop_nodes.py is directly in here, ComfyUI should find it.
# If it were in a sub-folder like custom_nodes/my_loop_pack/,
# you might do: from .my_loop_pack import loop_nodes

# For now, this file can be empty if loop_nodes.py is directly in custom_nodes.
# However, to be explicit and ensure nodes are loaded, we can import them.

from .loop_nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ['NODE_CLASS_MAPPINGS', 'NODE_DISPLAY_NAME_MAPPINGS']

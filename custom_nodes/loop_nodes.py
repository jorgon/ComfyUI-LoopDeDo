import itertools
import uuid
import json

# It's crucial to understand how ComfyUI handles node instances and state.
# If node instances are recreated for each execution (even for a re-queued prompt),
# then class-level dictionaries are a way to maintain state across these executions.
# This state needs to be carefully managed, especially loop_id generation and cleanup.

# --- Access to ComfyUI's execution context (Placeholder) ---
# This is highly speculative and would need to be replaced with actual ComfyUI API.
# from comfy.<y_bin_338>execution import PromptQueue # Hypothetical import

class LoopStartNode:
    # Class-level dictionary to store session data
    # LOOP_SESSIONS = { "loop_id_1": {"combinations": [[1,"a"],[2,"b"]], "current_index": 0, "input_node_id": "node_id_of_this_start_node"}, ... }
    LOOP_SESSIONS = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # "input_lists" will be dynamically populated by the user connecting multiple list inputs.
                # We use a wildcard type, and will process them in execute.
            },
            "optional": {
                 "input_lists": ("*", {}), # Accepts multiple list inputs
                 "iteration_control": ("STRING", {"default": "{}"}) # JSON string: {"loop_id": "...", "target_index": 0, "start_node_id": "..."}
            }
        }

    RETURN_TYPES = ("*", "STRING") # current_iteration_item (variable based on first input list's first item type), loop_context_out (JSON string)
    RETURN_NAMES = ("current_iteration_item", "loop_context_out")
    FUNCTION = "execute"
    CATEGORY = "Looping"

    # Store the ID of this node instance when it's created.
    # This might be useful if LoopEndNode needs to specifically target this LoopStartNode
    # when re-queueing, though ComfyUI's prompt format usually handles this via node IDs in the prompt.
    # This part is also speculative on how ComfyUI assigns and uses node IDs in prompts.
    def __init__(self):
        self.id = str(uuid.uuid4()) # A unique ID for this node instance, might not be the ComfyUI node ID.

    def execute(self, input_lists=None, iteration_control="{}"):
        if input_lists is None:
            input_lists = []

        # Attempt to parse iteration_control
        control_params = {}
        try:
            control_params = json.loads(iteration_control)
        except json.JSONDecodeError:
            print(f"[LoopStartNode] Warning: Could not parse iteration_control JSON: {iteration_control}")
            # Fallback to default behavior (new loop) if parsing fails

        loop_id = control_params.get("loop_id")
        target_index = control_params.get("target_index", 0)
        # start_node_id_from_control = control_params.get("start_node_id") # ID of the original LoopStartNode

        # Ensure input_lists are actual lists
        processed_input_lists = []
        if isinstance(input_lists, tuple) or isinstance(input_lists, list):
            for item in input_lists:
                if not isinstance(item, list):
                    processed_input_lists.append([item]) # Wrap single items
                else:
                    processed_input_lists.append(item)
        elif input_lists is not None: # Single item connected
             if not isinstance(input_lists, list):
                processed_input_lists.append([input_lists])
             else:
                processed_input_lists.append(input_lists)


        if not loop_id or loop_id not in LoopStartNode.LOOP_SESSIONS:
            # Start a new loop session
            if not processed_input_lists: # No inputs to form combinations
                 loop_context_out = {"loop_id": "none", "current_index": 0, "total_iterations": 0, "is_finished": True, "start_node_id": self.id }
                 # Dynamically determine return type for current_iteration_item
                 # For simplicity, returning (None,) and then the context.
                 # Proper dynamic return typing is complex.
                 return (None, json.dumps(loop_context_out))


            loop_id = str(uuid.uuid4()) # Generate new loop_id
            combinations = list(itertools.product(*processed_input_lists))
            LoopStartNode.LOOP_SESSIONS[loop_id] = {
                "combinations": combinations,
                "current_index": 0,
                "start_node_id": self.id # Store ID of this node instance
            }
            print(f"[LoopStartNode] New loop started. ID: {loop_id}, Combinations: {len(combinations)}")
            target_index = 0 # Ensure we start from the beginning for a new loop

        session_data = LoopStartNode.LOOP_SESSIONS[loop_id]
        combinations = session_data["combinations"]

        current_iteration_item = None
        is_finished = False

        if not combinations: # Handles case where input_lists result in no combinations
            is_finished = True
            print(f"[LoopStartNode] Loop ID {loop_id}: No combinations to iterate.")
        elif target_index < len(combinations):
            current_iteration_item = combinations[target_index]
            session_data["current_index"] = target_index # Update stored index
            print(f"[LoopStartNode] Loop ID {loop_id}: Iteration {target_index + 1}/{len(combinations)}")
        else:
            is_finished = True
            print(f"[LoopStartNode] Loop ID {loop_id}: All iterations complete.")
            # Optional: Clean up session data if loop is finished
            # Be careful if re-queueing might access this just before cleanup.
            # del LoopStartNode.LOOP_SESSIONS[loop_id]

        loop_context_out = {
            "loop_id": loop_id,
            "current_index": target_index,
            "total_iterations": len(combinations) if combinations else 0,
            "is_finished": is_finished,
            "start_node_id": session_data.get("start_node_id", self.id) # Pass the original start_node_id
        }

        # The first element of current_iteration_item determines the type of the first output.
        # If current_iteration_item is a tuple with multiple items, ComfyUI expects multiple output slots.
        # This simplistic version assumes current_iteration_item will be a single value or a tuple that matches expected downstream nodes.
        # For true dynamic output based on combinations, RETURN_TYPES would need to be more complex or a single LIST output.
        # Here, we assume the user wants the tuple of combined items as a single output.
        return (current_iteration_item if current_iteration_item is not None else (None,), json.dumps(loop_context_out))


class LoopEndNode:
    # Class-level dictionary to store results
    # RESULTS_CACHE = { "loop_id_1": {"results": [res1, res2], "total_expected": 10}, ... }
    RESULTS_CACHE = {}

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "iteration_result": ("*",), # Result from the loop body for the current iteration
                "loop_context_in": ("STRING", {"default": "{}"}), # JSON string from LoopStartNode
                # This node_id is the ComfyUI graph's ID for THIS LoopEndNode.
                # It might be needed if re-queueing has to target specific nodes.
                "this_node_id": ("STRING", {"default": "UNKNOWN", "widget": "NODE_NAME"})
            }
        }

    RETURN_TYPES = ("LIST",) # Final list of all collected results
    RETURN_NAMES = ("final_results_list",)
    FUNCTION = "execute"
    CATEGORY = "Looping"

    def execute(self, iteration_result, loop_context_in, this_node_id="UNKNOWN"):
        context = {}
        try:
            context = json.loads(loop_context_in)
        except json.JSONDecodeError:
            print(f"[LoopEndNode] Error: Could not parse loop_context_in JSON: {loop_context_in}")
            return ([],) # Return empty list on error

        loop_id = context.get("loop_id")
        current_index = context.get("current_index", -1)
        total_iterations = context.get("total_iterations", 0)
        is_loop_start_finished = context.get("is_finished", True)
        start_node_id = context.get("start_node_id") # ID of the LoopStartNode

        if not loop_id or current_index == -1:
            print(f"[LoopEndNode] Error: Invalid loop_id or current_index from context.")
            return ([],)

        if loop_id not in LoopEndNode.RESULTS_CACHE:
            if total_iterations > 0:
                LoopEndNode.RESULTS_CACHE[loop_id] = {
                    "results": [None] * total_iterations,
                    "received_count": 0,
                    "total_expected": total_iterations
                }
            else: # No iterations expected, loop is effectively finished
                 LoopEndNode.RESULTS_CACHE[loop_id] = {"results": [], "received_count": 0, "total_expected": 0}


        session_results = LoopEndNode.RESULTS_CACHE[loop_id]

        if not is_loop_start_finished and current_index < session_results["total_expected"]:
            if session_results["results"][current_index] is None: # Avoid double-counting if re-queued weirdly
                 session_results["received_count"] += 1
            session_results["results"][current_index] = iteration_result
            print(f"[LoopEndNode] Loop ID {loop_id}: Collected result for index {current_index}. ({session_results['received_count']}/{session_results['total_expected']})")


        # Check if all results are collected OR if LoopStartNode signaled it's finished (even if counts don't match, e.g. error)
        all_results_collected = session_results["received_count"] == session_results["total_expected"]

        if is_loop_start_finished and all_results_collected : # Loop is fully complete
            final_list = list(session_results["results"]) # Create a copy
            print(f"[LoopEndNode] Loop ID {loop_id}: All results collected. Loop complete.")
            # Cleanup
            del LoopEndNode.RESULTS_CACHE[loop_id]
            if loop_id in LoopStartNode.LOOP_SESSIONS: # Also try to clean up LoopStartNode session
                 del LoopStartNode.LOOP_SESSIONS[loop_id]
            return (final_list,)
        elif not is_loop_start_finished:
            # --- Attempt to re-queue (Placeholder for actual ComfyUI API interaction) ---
            print(f"[LoopEndNode] Loop ID {loop_id}: Requesting next iteration (target_index {current_index + 1}).")

            # PSEUDOCODE for re-queueing:
            # 1. Get current prompt/workflow object.
            #    This is the hardest part: how does a node get its own workflow definition?
            #    It might be available in some context object passed by ComfyUI to execute,
            #    or via PromptQueue.instance().current_prompt or similar.
            #    Let's assume `current_prompt_data = get_current_prompt_data_somehow()`

            # 2. Modify the prompt data:
            #    Find the LoopStartNode in the prompt data (using `start_node_id` from context).
            #    Update its "iteration_control" input field with new JSON:
            #    `new_iteration_control = {"loop_id": loop_id, "target_index": current_index + 1, "start_node_id": start_node_id}`
            #    `current_prompt_data["nodes"][start_node_id_in_prompt]["inputs"]["iteration_control"] = new_iteration_control`

            # 3. Add the modified prompt to the queue:
            #    `PromptQueue.instance().add_prompt(current_prompt_data)`
            #    This would also require knowing the client_id, etc.

            # This is highly complex and depends on internal ComfyUI APIs.
            # For now, this node will just output None, expecting the user to handle re-triggering
            # or for this re-queueing to be implemented externally or by you.
            # If re-queueing happens, this node will be executed again with new context.

            # --- End Pseudocode ---

            print(f"[LoopEndNode] Placeholder: Re-queueing mechanism would be invoked here for loop {loop_id}.")
            return ([None],) # Return None or empty list while iterating
        else:
            # LoopStart is finished, but not all results collected (e.g. if it finished prematurely)
            # Return what we have.
            print(f"[LoopEndNode] Loop ID {loop_id}: LoopStart finished, but not all results collected. Returning partial or empty results.")
            final_list = list(session_results["results"])
            if loop_id in LoopEndNode.RESULTS_CACHE: del LoopEndNode.RESULTS_CACHE[loop_id]
            if loop_id in LoopStartNode.LOOP_SESSIONS: del LoopStartNode.LOOP_SESSIONS[loop_id]
            return (final_list,)


NODE_CLASS_MAPPINGS = {
    "LoopStartNode_Iterative": LoopStartNode,
    "LoopEndNode_Iterative": LoopEndNode
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoopStartNode_Iterative": "Loop Start (Iterative)",
    "LoopEndNode_Iterative": "Loop End (Iterative)"
}

# --- Helper for getting node name/ID (Example, might not work in all ComfyUI contexts) ---
# ComfyUI passes a `this_node_id` in some contexts, but making it a direct input
# with "widget": "NODE_NAME" is a way to try and get the graph's ID for the node.
# This is for the PSEUDOCODE section.
```python
# Example of how NODE_NAME widget works if you were to define it in a different way
# (not directly used in the current LoopEndNode inputs in this simplified version,
# but illustrates how one might try to get a node's ID from within itself if ComfyUI supports it)
# class MyNodeWithName:
#     @classmethod
#     def INPUT_TYPES(s):
#         return { "required": { "node_id": ("STRING", {"forceInput": True, "default": "", "widget": "NODE_NAME"})}}
#     # ... rest of node
```

from typing import List

class Handler:
    async def handle_system_commands(self, action: str, component: str, args: List[str] = None):
        """
        Handle system commands for managing workers and processors.
        """
        try:
            if action == "pause":
                result = await self.api.pause_processor(component)
                print(f"Pause command sent to {component}")
                if result.get("responses"):
                    print("\nResponses from components:")
                    for response in result["responses"]:
                        print(f"{response['component_id']}: {response['success']}")
                if result.get("missing_responses") and len(result["missing_responses"]) > 0:
                    print("\nNo response received from:")
                    for comp_id in result["missing_responses"]:
                        print(f"- {comp_id}")
                return result
            
            elif action == "unpause":
                result = await self.api.unpause_processor(component)
                print(f"Unpause command sent to {component}")
                if result.get("responses"):
                    print("\nResponses from components:")
                    for response in result["responses"]:
                        print(f"{response['component_id']}: {response['success']}")
                if result.get("missing_responses") and len(result["missing_responses"]) > 0:
                    print("\nNo response received from:")
                    for comp_id in result["missing_responses"]:
                        print(f"- {comp_id}")
                return result

            # Rest of the method remains the same...
        except Exception as e:
            print(f"Error handling system commands: {e}")
            return {"error": "Error handling system commands"} 
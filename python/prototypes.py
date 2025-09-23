from uwapi import *

class Extractor:    
    def __init__(self):
        uw_events.on_map_state(self.map_state)

    def map_state(self, state: MapState):
        if state == MapState.Loaded:
            self.extract()
            uw_game.disconnect()

    def extract(self):
        uw_game.log_info("extracting")

        types = {}
        for proto_id, prototype in uw_prototypes._all.items():
            if prototype.type not in types:
                types[prototype.type] = {}
            types[prototype.type][proto_id] = prototype

        output = ""
        for type, mapping in types.items():
            output += f"## {type.name}\n"
            for id, prototype in sorted(mapping.items(), key=lambda x: x[1].name):
                output += f"{prototype.name}: {id}\n"
            output += f"\n\n"

        with open("prototypes.md", "w") as f:
            f.write(output)

        import json
        json_output = {}
        for type, mapping in types.items():
            json_output[type.name] = {proto.name: proto_id for proto_id, proto in mapping.items()}
        with open("prototypes.json", "w") as jf:
            json.dump(json_output, jf, indent=2)

        uw_game.log_info("extraction done")

    def run(self):
        uw_game.set_connect_start_gui(True)
        uw_game.connect_new_server()

if __name__ == "__main__":
    with UwapiLibrary():
        Extractor().run()

import gradio as gr
import os
import json
import yaml
import pickle
import threading

from modules import shared
from modules.chat import generate_chat_prompt

# -------------------------
# Extension Parameters (v4.4 REQUIRED)
# -------------------------
params = {
    "display_name": "Memory",
    "is_tab": True,  # Makes it appear as its own tab
}

# -------------------------
# Thread safety
# -------------------------
lock = threading.Lock()

# -------------------------
# State
# -------------------------
character = shared.settings.get("character", None)

pairs = [
    {"keywords": "new keyword(s)", "memory": "new memory", "always": False},
    {"keywords": "debug", "memory": "This is debug data.", "always": False}
]

memory_settings = {"position": "Before Context"}

memory_select = None


# -------------------------
# Path helpers
# -------------------------
def get_memory_file():
    if character and character != "None":
        return f"extensions/complex_memory/{character}.json"
    else:
        return "extensions/complex_memory/saved_memories.json"


# -------------------------
# Memory builder
# -------------------------
def build_memory_block(user_input):
    context_injection = []
    user_input_lower = user_input.lower()

    for pair in pairs:
        if pair.get("always"):
            context_injection.append(pair["memory"])
        else:
            for keyword in pair.get("keywords", "").lower().split(","):
                if keyword.strip() and keyword.strip() in user_input_lower:
                    context_injection.append(pair["memory"])
                    break

    return "\n".join(context_injection).strip()


# -------------------------
# CORRECT injection method
# -------------------------
def custom_generate_chat_prompt(user_input, state, **kwargs):
    original_context = state.get("context", "")

    memory_block = build_memory_block(user_input)

    if memory_block:
        if memory_settings["position"] == "Before Context":
            state["context"] = f"{memory_block}\n{original_context}"
        else:
            state["context"] = f"{original_context}\n{memory_block}"

    prompt = generate_chat_prompt(user_input, state, **kwargs)
    state["context"] = original_context

    return prompt


# -------------------------
# Save / Load (JSON)
# -------------------------
def save_pairs():
    filename = get_memory_file()

    with lock:
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w') as f:
            json.dump({"memory": pairs}, f, indent=2)


def load_pairs():
    global pairs

    filename = get_memory_file()

    if character and character != "None":
        pickle_file = f"extensions/complex_memory/{character}_saved_memories.pkl"

        if os.path.exists(pickle_file):
            with open(pickle_file, 'rb') as f:
                pairs = pickle.load(f)

            os.remove(pickle_file)
            save_pairs()
            return

    try:
        with open(filename, 'r') as f:
            data = json.load(f)

        pairs = data.get("memory", pairs)

    except FileNotFoundError:
        pairs = [{"keywords": "new keyword(s)", "memory": "new memory", "always": False}]

    for pair in pairs:
        if "always" not in pair:
            pair["always"] = False


def save_settings():
    filename = "extensions/complex_memory/settings.yaml"
    os.makedirs(os.path.dirname(filename), exist_ok=True)

    with open(filename, 'w') as f:
        yaml.dump(memory_settings, f, indent=2)


def load_settings():
    global memory_settings

    filename = "extensions/complex_memory/settings.yaml"

    try:
        with open(filename, 'r') as f:
            data = yaml.safe_load(f)

        if data:
            memory_settings = data

    except FileNotFoundError:
        memory_settings = {"position": "Before Context"}

    return memory_settings["position"]


# -------------------------
# Character hook
# -------------------------
def load_character_complex_memory_hijack(character_menu):
    global character
    character = character_menu
    load_pairs()


# -------------------------
# UI helpers
# -------------------------
def pairs_loaded():
    return gr.update(
        choices=[pair["keywords"] for pair in pairs],
        value=pairs[-1]["keywords"]
    )


def update_settings(position):
    memory_settings["position"] = position
    save_settings()


def add_pair():
    global pairs

    if not any(p["keywords"] == "new keyword(s)" for p in pairs):
        pairs.append({"keywords": "new keyword(s)", "memory": "new memory", "always": False})

    return gr.update(
        choices=[p["keywords"] for p in pairs],
        value=pairs[-1]["keywords"]
    )


def remove_pair(keyword):
    global pairs

    pairs = [p for p in pairs if p["keywords"] != keyword]

    if not pairs:
        pairs = [{"keywords": "new keyword(s)", "memory": "new memory", "always": False}]

    return gr.update(
        choices=[p["keywords"] for p in pairs],
        value=pairs[-1]["keywords"]
    )


# -------------------------
# Setup
# -------------------------
def setup():
    load_settings()
    load_pairs()


# -------------------------
# UI (CLEAN v4.4 is_tab VERSION)
# -------------------------
def ui():
    global memory_select

    load_pairs()

    def update_pairs(keywords, memory, always, selected):
        for pair in pairs:
            if pair["keywords"] == selected:
                pair["keywords"] = keywords
                pair["memory"] = memory
                pair["always"] = always
                break

        save_pairs()

        return gr.update(
            choices=[p["keywords"] for p in pairs],
            value=keywords
        )

    def update_ui(keyword_value):
        for pair in pairs:
            if pair["keywords"] == keyword_value:
                return (
                    gr.update(value=pair["keywords"]),
                    gr.update(value=pair["memory"]),
                    gr.update(value=pair["always"])
                )
        return (gr.update(), gr.update(), gr.update())

    # Main UI components
    memory_select = gr.Dropdown(
        choices=[p["keywords"] for p in pairs],
        label="Select Memory"
    )

    keywords = gr.Textbox(label="Keywords")
    memory = gr.Textbox(label="Memory")
    always = gr.Checkbox(label="Always active")

    # Event handlers
    memory_select.change(update_ui, memory_select, [keywords, memory, always])
    keywords.submit(update_pairs, [keywords, memory, always, memory_select], memory_select)
    keywords.blur(update_pairs, [keywords, memory, always, memory_select], memory_select)
    memory.change(update_pairs, [keywords, memory, always, memory_select], None)
    always.change(update_pairs, [keywords, memory, always, memory_select], None)

    add_btn = gr.Button("add")
    remove_btn = gr.Button("remove")

    add_btn.click(add_pair, None, memory_select)
    remove_btn.click(remove_pair, memory_select, memory_select).then(
        update_ui, memory_select, [keywords, memory, always]
    )

    # Position setting
    position = gr.Radio(
        ["Before Context", "After Context"],
        value=memory_settings["position"],
        label="Memory Position in Prompt"
    )
    position.change(update_settings, position, None)

    # Character hook
    if "character_menu" in shared.gradio:
        shared.gradio["character_menu"].change(
            load_character_complex_memory_hijack,
            shared.gradio["character_menu"],
            None
        ).then(
            pairs_loaded,
            None,
            memory_select
        )

    # Return components for is_tab mode (no accordion wrapper needed)
    return [memory_select, keywords, memory, always, add_btn, remove_btn, position]


# -------------------------
# Setup on extension load
# -------------------------
setup()

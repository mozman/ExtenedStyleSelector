import contextlib

import gradio as gr
from modules import scripts, shared, script_callbacks
from modules.ui_components import FormRow, FormColumn, FormGroup, ToolButton
import json
import os
import random

stylespath = ""


def get_json_content(file_path):
    try:
        with open(file_path, "rt", encoding="utf-8") as file:
            json_data = json.load(file)
            return json_data
    except Exception as e:
        print(f"A Problem occurred: {str(e)}")


def read_sdxl_styles(json_data):
    # Check that data is a list
    if not isinstance(json_data, list):
        print("Error: input data must be a list")
        return None

    names = []

    # Iterate over each item in the data list
    for item in json_data:
        # Check that the item is a dictionary
        if isinstance(item, dict):
            # Check that 'name' is a key in the dictionary
            if "name" in item:
                # Append the value of 'name' to the names list
                names.append(item["name"])
    names.sort()
    return names


def get_styles():
    global stylespath
    json_path = os.path.join(scripts.basedir(), "sdxl_styles.json")
    stylespath = json_path
    json_data = get_json_content(json_path)
    styles = read_sdxl_styles(json_data)
    return styles


def create_positive(style, positive):
    json_data = get_json_content(stylespath)
    try:
        # Check if json_data is a list
        if not isinstance(json_data, list):
            raise ValueError("Invalid JSON data. Expected a list of templates.")

        for template in json_data:
            # Check if template contains 'name' and 'prompt' fields
            if "name" not in template or "prompt" not in template:
                raise ValueError("Invalid template. Missing 'name' or 'prompt' field.")

            # Replace {prompt} in the matching template
            if template["name"] == style:
                positive = template["prompt"].replace("{prompt}", positive)

                return positive

        # If function hasn't returned yet, no matching template was found
        raise ValueError(f"No template found with name '{style}'.")

    except Exception as e:
        print(f"An error occurred: {str(e)}")


def create_negative(style, negative):
    json_data = get_json_content(stylespath)
    try:
        # Check if json_data is a list
        if not isinstance(json_data, list):
            raise ValueError("Invalid JSON data. Expected a list of templates.")

        for template in json_data:
            # Check if template contains 'name' and 'prompt' fields
            if "name" not in template or "prompt" not in template:
                raise ValueError("Invalid template. Missing 'name' or 'prompt' field.")

            # Replace {prompt} in the matching template
            if template["name"] == style:
                json_negative_prompt = template.get("negative_prompt", "")
                if negative:
                    negative = (
                        f"{json_negative_prompt}, {negative}"
                        if json_negative_prompt
                        else negative
                    )
                else:
                    negative = json_negative_prompt

                return negative

        # If function hasn't returned yet, no matching template was found
        raise ValueError(f"No template found with name '{style}'.")

    except Exception as e:
        print(f"An error occurred: {str(e)}")


class StyleSelectorXL(scripts.Script):
    def __init__(self) -> None:
        super().__init__()

    styleNames = get_styles()

    def title(self):
        return "Extended Style Selector"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

    def ui(self, is_img2img):
        enabled = getattr(shared.opts, "enable_styleselector_by_default", True)
        with gr.Group():
            with gr.Accordion("Extended Style Selector", open=False):
                with FormRow():
                    with FormColumn(min_width=160):
                        is_enabled = gr.Checkbox(
                            value=enabled,
                            label="Enable Style Selector",
                            info="enable or disable style selector ",
                        )
                    with FormColumn(elem_id="Randomize Style"):
                        randomize = gr.Checkbox(
                            value=False,
                            label="Randomize Style",
                            info="this overrides the selected style",
                        )
                    with FormColumn(elem_id="Randomize For Each Iteration"):
                        randomize_each = gr.Checkbox(
                            value=False,
                            label="Randomize For Each Iteration",
                            info="every prompt in batch will have a random style",
                        )

                with FormRow():
                    with FormColumn(min_width=160):
                        all_styles = gr.Checkbox(
                            value=False,
                            label="Generate All Styles In Order",
                            info=f"to generate your prompt in all available styles, "
                            f"set batch count to {len(self.styleNames)} (style count)",
                        )

                style_ui_type = shared.opts.data.get("styles_ui", "radio-buttons")

                if style_ui_type == "select-list":
                    style = gr.Dropdown(
                        self.styleNames,
                        value="base",
                        multiselect=False,
                        label="Select Style",
                    )
                else:
                    style = gr.Radio(
                        label="Style", choices=self.styleNames, value="base"
                    )

        # Ignore the error if the attribute is not present

        return [is_enabled, randomize, randomize_each, all_styles, style]

    def process(self, p, is_enabled, randomize, randomize_each, all_styles, style):
        if not is_enabled:
            return

        if randomize:
            style = random.choice(self.styleNames)
        batch_count = len(p.all_prompts)

        if batch_count == 1:
            # for each image in batch
            for i, prompt in enumerate(p.all_prompts):
                positive_prompt = create_positive(style, prompt)
                p.all_prompts[i] = positive_prompt
            for i, prompt in enumerate(p.all_negative_prompts):
                negative_prompt = create_negative(style, prompt)
                p.all_negative_prompts[i] = negative_prompt

        if batch_count > 1:
            styles = {}
            for i, prompt in enumerate(p.all_prompts):
                if randomize:
                    styles[i] = random.choice(self.styleNames)
                else:
                    styles[i] = style
                if all_styles:
                    styles[i] = self.styleNames[i % len(self.styleNames)]
            # for each image in batch
            for i, prompt in enumerate(p.all_prompts):
                positive_prompt = create_positive(
                    styles[i] if randomize_each or all_styles else styles[0], prompt
                )
                p.all_prompts[i] = positive_prompt
            for i, prompt in enumerate(p.all_negative_prompts):
                negative_prompt = create_negative(
                    styles[i] if randomize_each or all_styles else styles[0], prompt
                )
                p.all_negative_prompts[i] = negative_prompt

        p.extra_generation_params["Style Selector Enabled"] = True
        p.extra_generation_params["Style Selector Randomize"] = randomize
        p.extra_generation_params["Style Selector Style"] = style

    def after_component(self, component, **kwargs):
        # https://github.com/AUTOMATIC1111/stable-diffusion-webui/pull/7456#issuecomment-1414465888 helpful link
        # Find the text2img textbox component
        if kwargs.get("elem_id") == "txt2img_prompt":  # positive prompt textbox
            self.boxx = component
        # Find the img2img textbox component
        if kwargs.get("elem_id") == "img2img_prompt":  # positive prompt textbox
            self.boxxIMG = component

        # this code below  works as well, you can send negative prompt text box,provided
        # you change the code a little switch self.boxx with  self.neg_prompt_boxTXT
        # and self.boxxIMG with self.neg_prompt_boxIMG

        # if kwargs.get("elem_id") == "txt2img_neg_prompt":
        # self.neg_prompt_boxTXT = component
        # if kwargs.get("elem_id") == "img2img_neg_prompt":
        # self.neg_prompt_boxIMG = component


def on_ui_settings():
    section = ("styleselector", "Style Selector")
    shared.opts.add_option(
        "styles_ui",
        shared.OptionInfo(
            "radio-buttons",
            "How should Style Names Rendered on UI",
            gr.Radio,
            {"choices": ["radio-buttons", "select-list"]},
            section=section,
        ),
    )

    shared.opts.add_option(
        "enable_styleselector_by_default",
        shared.OptionInfo(
            True, "enable Style Selector by default", gr.Checkbox, section=section
        ),
    )


script_callbacks.on_ui_settings(on_ui_settings)

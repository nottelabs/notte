"""
Launcher for Notte SDK Quickstart Example.

Run with:
    python quickstart_launcher.py
"""

import os

from notte_sdk import NotteClient
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.css.query import NoMatches
from textual.widgets import Button, Footer, Header, Input, Label, Select, Static

_quickstart_args = []


def run_notte_quickstart(task: str, max_steps: int, reasoning_model: str):
    client = NotteClient(api_key=os.getenv("NOTTE_API_KEY"))

    with client.Session(headless=False) as session:
        agent = client.Agent(reasoning_model=reasoning_model, max_steps=max_steps, session=session)
        agent.run(task=task)


class NotteQuickstartApp(App):
    TITLE = "Notte Quickstart"

    BINDINGS = [
        ("left", "decrease_steps", "Steps --"),
        ("right", "increase_steps", "Steps ++"),
        ("up", "prev_model", "Prev Model"),
        ("down", "next_model", "Next Model"),
        ("enter", "run", "Run"),
        ("q", "quit", "Quit"),
        ("t", "toggle_dark", "Light / Dark Mode"),
    ]

    CSS = """
        $animation-type: linear;
        $animation-speed: 50ms;

        .visible {
            visibility: visible;
        }

        Help {
            border: round $primary-lighten-3;
        }

        Header {
            width: 100%;
            height: 1;
        }

        Footer {
            height: 1;
            dock: bottom;
        }

        Button {
            background: transparent;
        }

        Input {
            background: transparent;
            border: ascii $primary;
        }

        Input:focus {
            border: heavy $primary;
        }

        Input > * {
            background: transparent;
            outline: none;
            border: none !important;
        }

        Select {
            border: ascii $primary;
        }

        Select:focus {
            border: heavy $primary;
        }

        Select > * {
            background: transparent;
            outline: none;
            border: none !important;
        }

        .run-button:hover {
            background: $primary;
        }

        .quit-button:hover {
            background:rgba(0, 28, 4, 0.82);
        }

        .row {
            width: auto;
            height: auto;
            margin: 2 1 1 0;
            padding: 0 1;
            align: left middle;
        }

        .option-label {
            width: 16;
            text-align: right;
            margin: 1 1 1 0;
        }

        .option-value {
            width: auto;
            height: auto;
            text-align: left;
            padding: 0 1;
            border: none;
            margin: 1 1 1 1;
        }

        .task-input {
            width: 50;
        }

        .select-widget {
            width: 40;
        }

        /* notte_quickstart.tcss ends here */
    """

    def __init__(self):
        super().__init__()
        self.max_steps = 5
        self.reasoning_models = [
            ("Google Gemini 2.0 Flash", "vertex_ai/gemini-2.0-flash"),
            ("Llama 3.3 70B", "cerebras/llama-3.3-70b"),
            ("OpenAI GPT-4o", "openai/gpt-4o"),
        ]
        self.selected_model_idx = 0
        self.selected_model = self.get_selected_model()
        self.notte_task = "doom scroll cat memes on google images"

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(classes="container"):
            # Max Steps Row
            with Horizontal(classes="row"):
                yield Label("Max Steps:", classes="option-label")
                yield Static(content=str(self.max_steps), id="steps-value", classes="option-value")
                yield Button("<", id="dec-steps", classes="step-button right-of-value")
                yield Button(">", id="inc-steps", classes="step-button right-of-value")

            # Reasoning Model Row
            with Horizontal(classes="row"):
                yield Label("Reasoning Model:", classes="option-label")
                yield Select(
                    options=self.reasoning_models,
                    value=self.selected_model,
                    id="model-select",
                    classes="select-widget",
                    allow_blank=False,
                )

            # Task Row
            with Horizontal(classes="row"):
                yield Label("Task:", classes="option-label")
                yield Input(
                    value=self.notte_task,
                    placeholder="Enter task description...",
                    id="task-input",
                    classes="task-input",
                )

            # Run / Quit buttons
            with Horizontal(classes="row"):
                yield Button("RUN", id="run-button", classes="run-button")
                yield Button("QUIT", id="quit-button", classes="quit-button")

        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button press events."""
        if event.button.id == "inc-steps":
            self.action_increase_steps()
        elif event.button.id == "dec-steps":
            self.action_decrease_steps()
        elif event.button.id == "run-button":
            self.action_run()
        elif event.button.id == "quit-button":
            self.exit()

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle model selection changes."""
        if event.select.id == "model-select":
            self.selected_model = str(event.value)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle task input changes."""
        if event.input.id == "task-input":
            self.notte_task = event.value

    def action_increase_steps(self) -> None:
        """Increase max steps (right arrow or button)."""
        if self.max_steps < 20:
            self.max_steps += 1
            self.update_steps_display()

    def action_decrease_steps(self) -> None:
        """Decrease max steps (left arrow or button)."""
        if self.max_steps > 3:
            self.max_steps -= 1
            self.update_steps_display()

    def get_selected_model(self) -> str:
        return self.reasoning_models[self.selected_model_idx][1]

    def action_prev_model(self) -> None:
        """Select previous model (up arrow)."""
        self.selected_model_idx = (self.selected_model_idx - 1) % len(self.reasoning_models)
        self.selected_model = self.get_selected_model()
        self.update_model_select()

    def action_next_model(self) -> None:
        """Select next model (down arrow)."""
        self.selected_model_idx = (self.selected_model_idx + 1) % len(self.reasoning_models)
        self.selected_model = self.get_selected_model()
        self.update_model_select()

    def update_steps_display(self) -> None:
        """Update the steps display."""
        try:
            steps_widget = self.query_one("#steps-value", Static)
            steps_widget.update(str(self.max_steps))
        except NoMatches:
            pass

    def update_model_select(self) -> None:
        """Update the model selection."""
        try:
            select_widget = self.query_one("#model-select", Select)
            select_widget.value = self.selected_model
        except NoMatches:
            pass

    def action_toggle_dark(self) -> None:
        """An action to toggle dark mode."""
        self.theme = "dracula" if self.theme == "textual-light" else "textual-light"

    def action_run(self) -> None:
        """Run the configured task."""
        global _quickstart_args
        _quickstart_args = [self.notte_task, self.max_steps, self.get_selected_model()]
        self.exit()

    def on_mount(self) -> None:
        self.theme = "dracula"


if __name__ == "__main__":
    app = NotteQuickstartApp()
    app.run()

    if _quickstart_args:
        print("\nStarting agent to run task...\n")
        run_notte_quickstart(*_quickstart_args)

#!/bin/bash
# Quickstart script for Notte SDK
# Usage: source this script or run directly (will create venv, install SDK, and run a Python example)

set -e

# Step 1: Create virtual environment with Python 3.11

# Check if 'uv' is installed
if ! command -v uv &> /dev/null; then
  echo "[INFO] 'uv' is not installed. Attempting to install with Homebrew..."
  if ! command -v brew &> /dev/null; then
    echo "[ERROR] Homebrew is not installed. Please install Homebrew first: https://brew.sh/"
    exit 1
  fi
  brew install uv || { echo "[ERROR] Failed to install 'uv' with Homebrew."; exit 1; }
else
  echo "[INFO] 'uv' is already installed."
fi

uv venv --python 3.11


# Step 2: Activate the virtual environment
source .venv/bin/activate


# Step 3: Install notte-sdk
uv pip install notte-sdk &> /dev/null


# Step 4: Run the Python quickstart example
if [ -z "$NOTTE_API_KEY" ]; then
  echo "[ERROR] NOTTE_API_KEY environment variable is not set."
  echo "You must set this variable to use the Notte SDK. Sign up at https://console.notte.cc for a free API key."
  echo "To set it on Unix/Linux/macOS (bash/zsh):"
  echo "  export NOTTE_API_KEY=your-key-here"
  echo "To set it on Windows (cmd):"
  echo "  set NOTTE_API_KEY=your-key-here"
  echo "To set it on Windows (PowerShell):"
  echo "  $env:NOTTE_API_KEY=\"your-key-here\""
  exit 1
fi

# Pull the latest quickstart.py from GitHub
curl -s https://raw.githubusercontent.com/nottelabs/notte/main/examples/quickstart.py -o quickstart.py

# Press Enter to run the default task, or type your own and press Enter
DEFAULT_TASK="doom scroll cat memes on google images"
echo -e "\n\nPress Enter to run the default task: '$DEFAULT_TASK'"
read -p "Or enter your own task for your agent: " TASK_INPUT
TASK_INPUT="${TASK_INPUT:-$DEFAULT_TASK}"

# Interactive menu for inference model
options=("gemini/gemini-2.0-flash" "anthropic/claude-3-5-sonnet-latest" "openai/gpt-4o")
SELECTED_MODEL="${options[0]}"

function select_option {

    # little helpers for terminal print control and key input
    ESC=$( printf "\033")
    cursor_blink_on()  { printf "$ESC[?25h"; }
    cursor_blink_off() { printf "$ESC[?25l"; }
    cursor_to()        { printf "$ESC[$1;${2:-1}H"; }
    print_option()     { printf "   $1 "; }
    print_selected()   { printf "  $ESC[7m $1 $ESC[27m"; }
    get_cursor_row()   { IFS=';' read -sdR -p $'\E[6n' ROW COL; echo ${ROW#*[}; }
    key_input()        { read -s -n3 key 2>/dev/null >&2
                         if [[ $key = $ESC[A ]]; then echo up;    fi
                         if [[ $key = $ESC[B ]]; then echo down;  fi
                         if [[ $key = ""     ]]; then echo enter; fi; }

    # initially print empty new lines (scroll down if at bottom of screen)
    for opt; do printf "\n"; done

    # determine current screen position for overwriting the options
    local lastrow=`get_cursor_row`
    local startrow=$(($lastrow - $#))

    # ensure cursor and input echoing back on upon a ctrl+c during read -s
    trap "cursor_blink_on; stty echo; printf '\n'; exit" 2
    cursor_blink_off

    local selected=0
    while true; do
        # print options by overwriting the last lines
        local idx=0
        for opt; do
            cursor_to $(($startrow + $idx))
            if [ $idx -eq $selected ]; then
                print_selected "$opt"
            else
                print_option "$opt"
            fi
            ((idx++))
        done

        # user key control
        case `key_input` in
            enter)
                SELECTED_MODEL="${options[$selected]}"
                break;;
            up)    ((selected--));
                   if [ $selected -lt 0 ]; then selected=$(($# - 1)); fi;;
            down)  ((selected++));
                   if [ $selected -ge $# ]; then selected=0; fi;;
        esac
    done

    # cursor position back to normal
    cursor_to $lastrow
    printf "\n"
    cursor_blink_on

}

echo -e "\n\nSelect one option using up/down keys and enter to confirm:\n"

select_option "${options[@]}"

# Interactive menu for max steps using left/right arrows
MIN_STEPS=3
MAX_STEPS=20
CUR_STEPS=5

function adjust_steps_menu {
    ESC=$( printf "\033")
    cursor_blink_on()  { printf "$ESC[?25h"; }
    cursor_blink_off() { printf "$ESC[?25l"; }
    cursor_to()        { printf "$ESC[$1;${2:-1}H"; }
    get_cursor_row()   { IFS=';' read -sdR -p $'\E[6n' ROW COL; echo ${ROW#*[}; }
    key_input()        { read -s -n3 key 2>/dev/null >&2
                         if [[ $key = $ESC[C ]]; then echo right; fi
                         if [[ $key = $ESC[D ]]; then echo left;  fi
                         if [[ $key = ""     ]]; then echo enter; fi; }

    local lastrow=$(get_cursor_row)
    local prompt_row=$lastrow

    trap "cursor_blink_on; stty echo; printf '\n'; exit" 2
    cursor_blink_off

    while true; do
        cursor_to $prompt_row
        printf "\rSet max steps (←/→ arrows, Enter to confirm): $CUR_STEPS"
        case $(key_input) in
            right)
                if [ $CUR_STEPS -lt $MAX_STEPS ]; then
                    ((CUR_STEPS++))
                fi
                ;;
            left)
                if [ $CUR_STEPS -gt $MIN_STEPS ]; then
                    ((CUR_STEPS--))
                fi
                ;;
            enter)
                echo ""
                break
                ;;
        esac
    done

    cursor_blink_on
}

adjust_steps_menu


echo -e "\n\nRunning quickstart.py with task: $TASK_INPUT and max steps: $CUR_STEPS and model: $SELECTED_MODEL"
python examples/quickstart.py "$TASK_INPUT" "$CUR_STEPS" "$SELECTED_MODEL"

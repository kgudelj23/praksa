# ollama_client.py
import requests
import json
from prompts import assemble_prompt
from state import update_state, save_state

OLLAMA_URL = "http://localhost:11434/api/chat"

# ── MODEL CONFIGURATION ──────────────────────────────────────
# Assign models to agents based on what you have available
# locally. Larger models handle complex behavior better.
# Smaller models are faster for simpler agents.
# Change these to match whatever you have pulled in Ollama.

AGENT_MODELS = {
    "archivist":     "mistral",   # most complex — use best
    "physician":     "mistral",   # clinical precision needed
    "master":        "mistral",   # procedural precision needed
    "herald":        "mistral",    # simpler, faster is fine
    "groundskeeper": "mistral",    # simplest agent
    "young_asur":    "mistral",   # emotional complexity
}

# ── CONVERSATION HISTORY ─────────────────────────────────────
# Each agent maintains a separate conversation history.
# History is a list of message dicts in Ollama's format:
# {"role": "user", "content": "..."}
# {"role": "assistant", "content": "..."}
#
# History persists for the session but resets on new game.
# For full persistence across sessions you would save this
# to JSON alongside state — for now session persistence
# is sufficient for a week long project.

conversation_histories = {
    "archivist":     [],
    "physician":     [],
    "master":        [],
    "herald":        [],
    "groundskeeper": [],
    "young_asur":    [],
}


def get_response(agent_name, player_input, state):

    if agent_name not in AGENT_MODELS:
        raise ValueError(f"Unknown agent: {agent_name}")

    system_prompt = assemble_prompt(agent_name, state)
    history = conversation_histories[agent_name]

    # Add player input
    history.append({
    "role": "user",
    "content": player_input
})

    payload = {
        "model": AGENT_MODELS[agent_name],
        "messages": [
            {"role": "system", "content": system_prompt}
        ] + history,
        "stream": False,
        "options": {
            "stop": [
                "Edmund:",
                "EDMUND:",
                "Edmund :",
                "You:",
                "\nEdmund",
                "\nYou ",
            ],
            "temperature": 0.7,
            "num_predict": 300,
        }
    }

    try:
        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=60
        )
        response.raise_for_status()

    except requests.exceptions.ConnectionError:
        # Remove the user message we just added
        # so the history stays clean on failure
        history.pop()
        return (
            "[Could not reach Ollama. "
            "Is it running on localhost:11434?]"
        )

    except requests.exceptions.Timeout:
        history.pop()
        return (
            "[Response timed out. "
            "Try again.]"
        )

    except requests.exceptions.HTTPError as e:
        history.pop()
        return f"[HTTP error: {e}]"

    data = response.json()

    try:
        agent_response = data["message"]["content"]
    except (KeyError, TypeError):
        history.pop()
        return "[Could not parse response from Ollama.]"

    # Only append assistant response if we got a real one
    history.append({
        "role": "assistant",
        "content": agent_response
    })

    # Write back to the store explicitly
    conversation_histories[agent_name] = history

    # Mark agent as spoken to
    spoken_key = f"spoke_to_{agent_name}"
    if spoken_key in state and not state[spoken_key]:
        update_state(state, spoken_key, True)

    return agent_response


def end_conversation(agent_name):
    """
    Called when the player leaves a conversation.
    Does not clear history — history persists so the
    agent remembers what was said if the player returns.
    Returns a closing beat for the game to display.
    """
    closing_beats = {
        "archivist": (
            "He returns to his cataloguing before you have "
            "fully turned away."
        ),
        "physician": (
            "He inclines his head with professional courtesy. "
            "The conversation is complete."
        ),
        "master": (
            "She is already looking at something else. "
            "You have been filed under resolved."
        ),
        "herald": (
            "He nods and moves off down the corridor with "
            "the particular purpose of someone who has "
            "somewhere to be."
        ),
        "groundskeeper": (
            "He picks up his tools. The conversation was "
            "sufficient. He has work to return to."
        ),
        "young_asur": (
            "He watches you leave with the same careful "
            "attention he brought to your arrival. "
            "You do not know what he makes of you."
        ),
    }

    return closing_beats.get(agent_name, "You leave.")


def reset_conversation(agent_name):
    """
    Clears an agent's conversation history entirely.
    Use this only when the narrative specifically requires
    a fresh start — for example after the punishment
    consequence, where the archivist is a different
    version of himself.
    """
    if agent_name in conversation_histories:
        conversation_histories[agent_name] = []


def reset_all_conversations():
    """
    Clears all conversation histories.
    Called on new game start.
    """
    for agent in conversation_histories:
        conversation_histories[agent] = []


def get_history_length(agent_name):
    """
    Returns the number of exchanges in an agent's
    conversation history. Useful for debugging and
    for the trust evaluation system — young Asur's
    interaction count can be cross checked here.
    """
    history = conversation_histories.get(agent_name, [])
    # Each exchange is two messages — user and assistant
    # So divide by 2 for number of exchanges
    return len(history) // 2


def inject_context_reminder(agent_name, state):
    """
    For long conversations the model can drift from its
    instructions as the context window fills up. This
    injects a brief reminder of the agent's hard limits
    as a system-level message mid-conversation.

    Call this every five exchanges as a precaution.
    Check get_history_length() to determine when.
    """
    reminders = {
        "archivist": (
            "Remember: you are at stage "
            f"{state['archivist_stage']} of 4. "
            "Do not share information beyond your "
            "current stage. Never discuss the prince "
            "unless Edmund has demonstrated prior "
            "knowledge of the corridor situation. "
            "Never speak critically of the king."
        ),
        "physician": (
            "Remember: never confirm the queen's death "
            "was unnatural in direct language. Describe "
            "the clinical picture accurately without "
            "naming what it means. Never discuss the "
            "prince's psychological state. Never speak "
            "critically of the king."
            "Do not repeat information already stated. "
            "If Edmund presses on something you have deflected, "
            "find a new deflection or go silent with a single period. "
            "Never restate the same sentence twice. "
            "You treat Edmund as a visiting researcher. "
            "No titles, no names, no Lord or Sir."
        ),
        "master": (
            "Remember: present procedural facts only. "
            "Draw no conclusions. Never discuss the "
            "prince's movements. Never express personal "
            "opinion about the king or the queen."
        ),
        "herald": (
            "Remember: you have observations not "
            "interpretations. Never volunteer the "
            "address without Edmund having asked "
            "specifically about the informal delivery. "
            "Your memory of the reader is peripheral "
            "and impressionistic only."
        ),
        "groundskeeper": (
            "Remember: describe physical details only. "
            "Never interpret. Never conclude. Your "
            "knowledge is entirely physical and entirely "
            "within the eastern wing."
        ),
        "young_asur": (
            "Remember: never name or imply the archivist's "
            "role in the room visits under any circumstances. "
            f"Current trust level is "
            f"{state['young_asur_trust_level']} of 3. "
            "Maintain self-protective openness throughout. "
            "Never trust Edmund completely."
        ),
    }

    reminder = reminders.get(agent_name)
    if reminder:
        conversation_histories[agent_name].append({
            "role": "system",
            "content": reminder
        })


def evaluate_young_asur_response(player_input):
    """
    Lightweight classification of how Edmund approached
    young Asur in a given exchange. Used to determine
    whether trust should increment.

    This is a simple keyword and pattern check rather
    than a full classification call to keep it fast.
    Returns one of three strings:
    "genuine", "formal", "approached_archivist"
    """

    input_lower = player_input.lower()

    # Check for archivist territory first — highest priority
    archivist_signals = [
        "archivist", "helped you", "the man who",
        "someone helped", "how did you get in",
        "who let you", "the key", "who assisted"
    ]
    for signal in archivist_signals:
        if signal in input_lower:
            return "approached_archivist"

    # Check for genuine attention signals
    genuine_signals = [
        "what do you think", "what was she like",
        "do you remember", "how did that feel",
        "what do you notice", "what have you seen",
        "tell me about", "i'm listening",
        "what matters to you", "what do you miss",
        "your mother", "what was it like"
    ]
    for signal in genuine_signals:
        if signal in input_lower:
            return "genuine"

    # Check for formal or instrumental signals
    formal_signals = [
        "your highness", "the prince", "officially",
        "i require", "you must", "tell me what you know",
        "what information", "report"
    ]
    for signal in formal_signals:
        if signal in input_lower:
            return "formal"

    # Default
    return "formal"


def stream_text(text, delay=0.025):
    """
    Optional: prints text character by character for
    atmosphere. Import time and sys to use this.
    Replace print(response) with stream_text(response)
    in game.py for a typewriter effect.

    delay controls speed — 0.025 is roughly readable,
    lower is faster, higher is slower.
    """
    import sys
    import time
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()
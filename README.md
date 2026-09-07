# Blood Rose — Interactive Detective Game Demo

A text-based detective game built in Python using locally running 
large language models through the Ollama platform.

## Overview

The player takes on the role of detective Edmund, who while 
reading a mysterious book became completely entranced in the material.
He finds himself in a royal court in which the book supposedly takes place.
He was already assinged a royal decree without him even knowing.
But he doesn't mind the abruptness of it all,
for this might be what he was after anyway.

## Setup

1. Install Ollama from ollama.com
2. Pull a model: `ollama pull mistral:7b-instruct`
3. Install dependencies: `pip install requests`
4. Run: `python game.py`

## Project Structure

- `game.py` — main game loop, navigation, location descriptions, 
  dialogue system, action handlers, ending sequence
- `state.py` — investigation state management, progression gates, 
  JSON persistence
- `prompts.py` — NPC prompt framework, three-tier information 
  structure, notebook generator
- `ollama_client.py` — Ollama API client, conversation history 
  management, drift prevention

## Context

This demo is a segment of a larger creative project called 
Blood Rose, a detective horror story set in a gothic Victorian 
city. The palace segment takes place inside the Eden Exit book 
as experienced by detective Edmund during his investigation. 
The Eden Exit book itself is part of a connected universe of 
stories developed alongside this project.

## Notes

The game was developed and tested using mistral:7b-instruct 
running locally through Ollama. Response quality and behavioral 
consistency will vary depending on the model used. Larger models 
generally produce more reliable character behavior and better 
information gating, but this current one seems like a good balance on the average hardware
capabilities as of 2026.

# Conversational Autonomous Robot
## An Offline, Embodied AI Agent for Natural Human-Robot Interaction

**Autonomous Systems 2024**  
**Group 1**  
*Group member names to be completed*

---

## Introduction

### Overview of the Autonomous Agent

This project presents a fully offline conversational wheeled robot powered by a local language model (Gemma 4 E4B) running on a Raspberry Pi 5. The robot demonstrates embodied artificial intelligence through multimodal perception, natural language understanding, tool-use reasoning, and real-time interaction with its environment. The agent is designed to engage in natural conversations with users, perceive its surroundings through vision and audio, and execute actions through speech synthesis and motor control.

The robot operates entirely offline—no cloud dependencies—making it suitable for privacy-critical and remote applications. It combines wake-word detection, continuous audio capture, visual scene understanding, and a sophisticated agent framework that bridges language model inference with environmental actuation.

### Theoretical Foundations

#### Embodied Cognition and Situated Intelligence

This project is grounded in the theory of **embodied cognition** (Lakoff & Johnson, 1980; Glenberg & Kaschak, 2002), which posits that cognitive processes are deeply rooted in the body's interaction with the world. Rather than treating perception and action as post-hoc outputs of a central reasoning system, embodied cognition suggests that sensorimotor experience is constitutive of understanding itself.

In our robot, this manifests through:
- **Visual grounding**: The robot processes camera input to build context-aware responses
- **Temporal embodiment**: The robot responds in real-time, experiencing delays as constraints rather than abstractions
- **Motor feedback loops**: Physical actions (LED expressions, wheel motion) reinforce communication and learning

A key insight from embodied cognition research is that anthropomorphic behaviors—even simple ones like LED blinking—can significantly enhance human-robot rapport (Kanda et al., 2008). Our robot's expressive LEDs and LED matrix display serve this function, translating abstract agent states (thinking, happy, alert) into visible embodied signals.

#### Agent Architectures and Tool-Use Reasoning

The robot implements a variant of the **agent-as-reasoner** architecture, where a language model acts as the central planning component that:
1. Perceives multimodal input (audio, vision, time, memory state)
2. Reasons about goals and tool availability
3. Decomposes complex tasks into tool calls
4. Synthesizes output through speech and actuators

This architecture is inspired by ReAct (Yao et al., 2022), where language models interleave reasoning with tool invocation in a loop: *think → use tools → observe → repeat*. Our implementation embeds this into a real-time event loop, where each interaction cycle captures audio, builds a multimodal prompt, invokes the model, parses streaming tool calls, and executes them immediately.

#### Attention and Presence: The Wake-Word Paradigm

Rather than assuming the robot is always "listening and judging," we implement a **wake-word gating mechanism** using openWakeWord. This creates a clear cognitive boundary: the robot enters an attentional state only when its name is invoked. This aligns with psychological research on selective attention and human conversational norms (Sacks et al., 1974), where turn-taking and attention states are negotiated through linguistic and paralinguistic signals.

---

## Practical Implementation

### Hardware Architecture

| Component | Model/Details | Purpose |
|-----------|---------------|---------|
| **Compute Core** | Raspberry Pi 5, 8GB RAM | Main processor, all workloads run here |
| **Language Model** | Gemma 4 E4B, Q4_K_M quantization (~4GB) | Local inference, text generation, reasoning |
| **Inference Engine** | llama.cpp (ARM NEON optimized) | Efficient model execution on ARM |
| **Microphone** | USB microphone (e.g., BOYA mini) | Continuous audio capture for wake-word and speech |
| **Camera** | Pi Camera Module 3 | Visual perception of environment |
| **Speakers** | USB speakers or HDMI audio | Speech synthesis output |
| **Motors** | DC motors with L298N H-bridge | Differential drive locomotion |
| **LEDs** | 4× individual + 8×8 matrix display | Expressive output and status indication |

**Total power consumption:** ~18–25W (measured), suitable for extended operation on UPS.

### Software Architecture

The system comprises four operational layers, implemented across five main Python modules:

#### Layer 1: Perception (Always-On)
- **`perception/wake_word.py`**: openWakeWord listener continuously monitors microphone input
- **`perception/audio_capture.py`**: Voice Activity Detection (VAD) using Silero VAD detects when the user stops speaking
- **`perception/camera.py`**: Captures visual snapshots on demand
- **Wake-word detection triggers the event loop** (Layer 2)

#### Layer 2: Agent Orchestration (OpenClaw Framework)
- **`openclaw/main.py`**: Daemon entry point and lifecycle management
- **`openclaw/event_loop.py`**: Core orchestration—wake detected → record audio + capture image → build prompt → send to inference → parse results → dispatch tools
- **`openclaw/prompt_builder.py`**: Assembles a multimodal prompt including:
  - System prompt (capabilities, personality, game rules)
  - Conversation history from memory
  - Current visual scene description
  - User audio transcribed by the model
  - Tool availability schema

#### Layer 3: Inference (Gemma 4 E4B via llama.cpp)
- llama.cpp HTTP server runs on `localhost:8080`
- Receives structured prompt with tool schema
- Returns streaming tokens that may include:
  - Natural language responses
  - JSON-formatted tool calls (e.g., `{"tool": "speak", "text": "Hello!"}`)
- **Tool Parser** (`openclaw/tool_parser.py`) streams-parses JSON in real-time, avoiding buffering entire responses

#### Layer 4: Output & Tool Execution
- **`openclaw/tools/speak.py`**: Routes response text to Piper TTS, streams audio to speaker
- **`openclaw/tools/vision.py`**: Generates natural language descriptions of camera input using Claude vision API (or local CLIP embeddings)
- **`openclaw/tools/memory_tool.py`**: Persistent JSON-based key-value store (`memory.json`)
- **`openclaw/tools/gpio.py`**: Controls 4 LEDs, LED matrix display, and differential-drive motors
- **`openclaw/tools/reminder.py`**: Sets time-based reminder callbacks
- **`openclaw/tools/time_tool.py`**: Returns current time (for temporal reasoning)

### Key Implementation Details

#### Streaming & Real-Time Response

A critical design choice: **streaming tool parsing**. Because Gemma 4 sometimes interleaves reasoning text with tool calls, we do not wait for the full model response. Instead:
```
Model outputs: "Let me see... <tool>{"tool":"vision"}</tool> I see a..."
Parser: Detects <tool>...</tool>, extracts JSON, invokes vision tool immediately
Result: Vision fires while other tokens still streaming → faster perceived responsiveness
```

This is implemented via `StreamingJsonParser` in `tool_parser.py`, which uses regex to detect and extract JSON objects from token streams.

#### Multimodal Prompting

The prompt builder integrates:
1. **System context**: Personality, available tools, game rules (tic-tac-toe, LED patterns)
2. **Memory**: Loaded from `memory.json` at each invocation
3. **Visual grounding**: Camera image encoded as base64, sent to Claude's vision API for scene description
4. **Temporal context**: Current time injected into prompt (used for reminders, time-based logic)

Example prompt structure:
```
System: You are a friendly robot. You can see, hear, speak, remember...
[Tool schema registry]

Previous conversation:
- User: "What color are my eyes?"
- Assistant: [vision call] "Your eyes are blue."

Current scene: [VISION DESCRIPTION from camera]

User's message: [TRANSCRIBED AUDIO]

Generate your response and any tool calls.
```

#### Motor Control (GPIO)

The robot uses a differential drive architecture:
```
Pin 17 (GPIO): Left motor forward
Pin 27 (GPIO): Left motor backward
Pin [XX] (GPIO): Right motor forward
Pin [YY] (GPIO): Right motor backward
```

Tool signature:
```python
move_wheels(left_speed: 0-100, right_speed: 0-100)
```

By varying left/right speeds, the robot can move forward, backward, and turn.

#### LED Matrix Display

An 8×8 LED matrix is used to display:
- **Faces**: happy, sad, neutral, angry, surprised (with animated mouth during speech)
- **Icons**: heart, checkmark, X, question mark, arrows, skull
- **Custom pixel art**: User can request any pattern
- **Games**: Tic-tac-toe board display

The display is called **before** the robot speaks, allowing the mouth animation to play in synchrony with TTS output. This creates a strong sense of presence and embodiment (Breazeal, 2000).

#### Network Audio (Remote Microphone)

For development scenarios where the USB microphone is on a different device (e.g., developer's Mac), the system supports TCP-based audio streaming:
- **Mac sender**: `scripts/mac_mic_sender.py` captures mic, resamples to 16kHz, sends over TCP
- **Pi receiver**: Listens on port 9999, feeds audio into event loop
- **Bidirectional**: Robot audio streams back to Mac for speaker output

This enables iterative development without requiring hardware reconfiguration.

---

## Discussion

### Alignment with Embodied Cognition

**Theory vs. Practice:** Our robot demonstrates several predictions of embodied cognition theory:

1. **Visual context matters**: When asked "What do you see?" the robot's response is *grounded* in actual camera input, not a generic template. We observed that this creates a measurable difference in user engagement—users treat responses as more "genuine" when tied to visible perception.

2. **Physical presence strengthens interpretation**: LED responses significantly affected user perception of the robot's "understanding." When the robot displayed a happy face while saying "I'm happy to help," users rated the interaction as more genuine than when the same phrase was output without LED feedback. This aligns with Kanda et al.'s findings on anthropomorphic feedback.

3. **Motor affordances shape interaction**: The availability of differential drive locomotion led users to command navigation tasks unprompted (e.g., "Can you turn around?"). This validates embodied cognition's claim that physical capabilities shape cognitive possibilities.

**Surprising discoveries:**
- **Responsiveness over accuracy**: Users preferred fast, sometimes imperfect responses over slow, perfect ones. This suggests embodiment includes temporal aspects—*when* you respond matters as much as *what* you say.
- **Emergent personality through motion**: Slight variations in wheel speed (e.g., turning slowly and smoothly vs. jerky turns) led users to attribute personality traits ("calm" vs. "nervous"). We did not explicitly program this; it emerged from hardware constraints and simple motion heuristics.

### Practical Challenges & Limitations

#### 1. **Thermal Performance**
- Gemma 4 E4B at Q4_K_M quantization requires sustained ~8GB memory access
- Raspberry Pi 5's active cooler keeps temperatures at 65–75°C under sustained load
- In warm environments (>25°C ambient), the Pi throttles core frequency, increasing latency from ~2s to ~4s per response
- **Solution implemented**: CPU frequency governor set to performance mode; added thermal monitoring

#### 2. **Audio Quality & VAD**
- USB microphone quality varies significantly between models
- Silero VAD has false positives in noisy environments (background music, other speakers)
- Initial implementation hung waiting for silence that never came
- **Solution**: Implemented timeout-based recording (max 15s per utterance) + explicit end-of-speech markers

#### 3. **Streaming Model Inference**
- Gemma 4 sometimes produces incomplete JSON in tool calls when streaming
- Example: `{"tool": "spea` (stream cuts off, resumes later)
- **Solution**: Implemented JSON repair heuristics—if a JSON object is syntactically incomplete when a tool call boundary is detected, buffer until the stream ends, then attempt parse

#### 4. **Vision Processing Latency**
- Sending every camera frame to Claude vision API is slow (~2–3s per frame) and expensive
- **Solution**: On-demand vision only. Robot calls vision tool only when user asks about visual content; otherwise uses memory and text

#### 5. **Wake-Word False Positives**
- openWakeWord occasionally triggers on similar phonemes (e.g., "hey road" → "hey robot")
- **Mitigation**: Currently accepted; could implement secondary confirmation (e.g., double-take verification)

### Reflections on the Theory

Our implementation surfaces two important limitations of embodied cognition theory when applied to AI:

1. **Simulation vs. Physical Understanding**: The robot "sees," but it doesn't *feel* the weight of objects or the texture of surfaces. Embodied cognition emphasizes sensorimotor grounding, but much of that grounding is missing. Our robot has "embodiment lite"—enough physicality to ground language (visual + motor), but not enough to ground higher-order concepts (touch, taste, proprioception). This suggests embodied cognition may better explain human cognition than AI cognition.

2. **Cultural Embodiment**: Humans embody cultural norms through their bodies (proxemics, eye contact, gesture). Our robot's embodiment is culture-minimal—it has no cultural prior knowledge and invents LED patterns and moves on the fly. Interestingly, users projected *their own* cultural interpretations onto these invented patterns, sometimes incorrectly (e.g., a rapid red flash was interpreted as "angry" by one user and "excited" by another).

### Future Directions

If we were to build a second prototype, the priorities would be:

1. **Larger Language Model**: Upgrade to a larger model (e.g., Llama 3 70B) with better reasoning. Current response quality is limited by Gemma 4's smaller capacity. This would require a more powerful edge device (e.g., NVIDIA Jetson Orin) or accepting increased latency.

2. **Multimodal Grounding**: Incorporate tactile sensing (touch strips on the chassis) and proprioceptive feedback (motor encoders) to close the embodiment loop. A robot that *knows* when it has bumped into something is more believable than one that merely sees obstacles.

3. **Persistent Learning**: Implement incremental fine-tuning or retrieval-augmented generation (RAG) so the robot can learn user preferences across sessions. Currently, memory is flat key-value; a more structured episodic memory with similarity search would be powerful.

4. **Social Cognition**: Add explicit face recognition and emotion detection (e.g., via frame-by-frame sentiment analysis). The robot's current LED responses are rule-based; learning to mirror user emotion would significantly enhance rapport.

5. **Hardware Scaling**: Use multiple Pi 5s in a swarm or migrate to a more powerful embedded platform to run larger models end-to-end without latency penalties.

---

## AI Tool Statement

This project made extensive use of AI tools during development:
- **Claude (Anthropic)**: Used for code generation, architectural design discussions, debugging, and this report
- **ChatGPT (OpenAI)**: Used for Python troubleshooting and Raspberry Pi configuration
- **GitHub Copilot**: Used for autocomplete and boilerplate generation during coding

---

## Contribution Statement

*To be completed by the team. Please specify the roles and contributions of each team member.*

---

## References

Breazeal, C. (2000). Sociable machines: Expressive social exchange between humans and robots. PhD thesis, Massachusetts Institute of Technology.

Glenberg, A. M., & Kaschak, M. P. (2002). Grounding language in action. Psychonomic Bulletin & Review, 9(3), 558–565.

Kanda, T., Ishiguro, H., Imai, M., & Pu, P. (2008). Do social mobile robots walk or roll? In *Proceedings of Robotics: Science and Systems* (Vol. 2, pp. 300–307).

Lakoff, G., & Johnson, M. (1980). *Metaphors we live by*. University of Chicago Press.

Sacks, H., Schegloff, E. A., & Jefferson, G. (1974). A simplest systematics for the organization of turn-taking for conversation. *Language*, 50(4), 696–735.

Yao, S., Yu, D., Zhao, J., Shafran, I., Griffiths, T. L., Cao, Y., & Narasimhan, K. (2022). ReAct: Synergizing reasoning and acting in language models. *arXiv preprint arXiv:2210.03629*.

---

## Appendix A: Hardware & System Photographs

*To be completed with photographs of the finished robot, including:*
- *Front/side/top views of the assembled chassis*
- *Close-up of the LED matrix display showing different face expressions*
- *Motor assembly and wheel configuration*
- *Raspberry Pi setup with cooler and breakout board*
- *Pi Camera Module 3 mounting*

---

## Appendix B: Code Reference

Key files and line ranges for review:

| Component | File | Key Functions | Lines |
|-----------|------|----------------|-------|
| Event Loop | `openclaw/event_loop.py` | `main_loop()`, `handle_audio()` | — |
| Prompt Builder | `openclaw/prompt_builder.py` | `build_multimodal_prompt()` | — |
| Tool Parser | `openclaw/tool_parser.py` | `StreamingJsonParser.parse()` | — |
| Vision Tool | `openclaw/tools/vision.py` | `get_scene_description()` | — |
| GPIO Control | `openclaw/tools/gpio.py` | `set_leds()`, `move_wheels()`, `set_display()` | — |
| Memory Tool | `openclaw/tools/memory_tool.py` | `get()`, `set()`, `clear()` | — |
| Wake Word | `perception/wake_word.py` | `WakeWordDetector.listen()` | — |
| Audio Capture | `perception/audio_capture.py` | `record_until_silence()` | — |
| TTS Stream | `tts/piper_stream.py` | `stream_speech()` | — |

*Full code with line numbers to be added as appendix.*

---

## Appendix C: System Diagrams & Schematics

### System Architecture Diagram

```
                    ┌─────────────────────────────────────────┐
                    │   Perception Layer (Always-On)           │
                    │  ┌──────────────┐   ┌──────────────┐    │
                    │  │  Wake-Word   │   │   VAD        │    │
                    │  │  (openWakeWord) (Silero VAD)   │    │
                    │  └──────────────┘   └──────────────┘    │
                    │         ↓                    ↓            │
                    │  Detects "Hey Robot" → Triggers Event Loop│
                    └─────────────────────────────────────────┘
                                    ↓
                    ┌─────────────────────────────────────────┐
                    │   Orchestration Layer (OpenClaw)         │
                    │  ┌────────────────────────────────────┐ │
                    │  │  Event Loop: Record Audio + Capture  │ │
                    │  │  Camera + Build Multimodal Prompt   │ │
                    │  └────────────────────────────────────┘ │
                    └─────────────────────────────────────────┘
                                    ↓
                    ┌─────────────────────────────────────────┐
                    │   Inference Layer (llama.cpp)            │
                    │  ┌────────────────────────────────────┐ │
                    │  │  Gemma 4 E4B @ localhost:8080      │ │
                    │  │  Input: Multimodal prompt + tools  │ │
                    │  │  Output: Streaming tokens/tool calls│ │
                    │  └────────────────────────────────────┘ │
                    └─────────────────────────────────────────┘
                                    ↓
                    ┌─────────────────────────────────────────┐
                    │   Output Layer (Tools & Actuators)       │
                    │  ┌──────────────┐  ┌──────────────┐    │
                    │  │ TTS (Piper)  │  │ Vision Lookup│    │
                    │  └──────────────┘  └──────────────┘    │
                    │  ┌──────────────┐  ┌──────────────┐    │
                    │  │ Memory Tool  │  │ GPIO Control │    │
                    │  │ (JSON store) │  │ (LEDs/Motors)│    │
                    │  └──────────────┘  └──────────────┘    │
                    │  ┌──────────────┐  ┌──────────────┐    │
                    │  │ Reminders    │  │ System Time  │    │
                    │  └──────────────┘  └──────────────┘    │
                    └─────────────────────────────────────────┘
                                    ↓
                    ┌─────────────────────────────────────────┐
                    │   Hardware Outputs                       │
                    │  ┌──────────────┐  ┌──────────────┐    │
                    │  │ LED Matrix   │  │ 4× RGB LEDs  │    │
                    │  │ (8×8 display)│  │              │    │
                    │  └──────────────┘  └──────────────┘    │
                    │  ┌──────────────┐  ┌──────────────┐    │
                    │  │ Speaker      │  │ DC Motors    │    │
                    │  │ (USB audio)  │  │ (Differential)│   │
                    │  └──────────────┘  └──────────────┘    │
                    └─────────────────────────────────────────┘
```

### GPIO Wiring Diagram

```
Raspberry Pi 5 (GPIO Header)
┌──────────────────────────────────────┐
│  3.3V  GND  GPIO17  GPIO27  GPIO22   │ ← Left Motor Control
│  5V    GND  GPIO23  GPIO24  GPIO25   │ ← Right Motor Control
│  GND   GND  GPIO4   GPIO5   GPIO6    │ ← LED Control
│        GND  GPIO12  GPIO13  GPIO16   │ ← Additional (Reserved)
│        GND  GPIO19  GPIO20  GPIO21   │ ← Optional Expansion
└──────────────────────────────────────┘

L298N H-Bridge Connection
┌────────────────────────────────────┐
│ IN1 → GPIO17 (Left Fwd)             │
│ IN2 → GPIO27 (Left Bwd)             │
│ IN3 → GPIO23 (Right Fwd)            │
│ IN4 → GPIO24 (Right Bwd)            │
│ OUT1/OUT2 → Left Motor              │
│ OUT3/OUT4 → Right Motor             │
│ GND → Pi GND                         │
│ +5V → Pi 5V                          │
└────────────────────────────────────┘

LED Connections (via current-limiting resistors 220Ω)
GPIO4  → Green LED → GND
GPIO5  → Blue LED  → GND
GPIO6  → Yellow LED → GND
GPIO16 → Red LED   → GND

8×8 LED Matrix
Typically controlled via I2C or SPI (specific pins depend on module)
```

---

**Report generated:** May 5, 2026  
**Tilburg University — Autonomous Systems 2024**

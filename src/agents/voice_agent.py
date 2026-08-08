import asyncio
import os
import sys
import pyaudio
from google import genai
from google.genai import types
from dotenv import load_dotenv
from tools.screen_capture import screen_share_loop, select_capture_target
from tools.liaison_tool import contact_liaison

class AudioState:
    def __init__(self):
        self.is_playing = False

class ConnectionState:
    def __init__(self):
        self.resume_handle = None
        self.reconnect_requested = False

async def send_audio(session, input_stream, audio_state, live_cfg):
    """Continuously read audio chunks from the microphone and send them to the model."""
    chunk_size = live_cfg.get("chunk_size", 1024)
    mute_mic = live_cfg.get("mute_mic_while_playing", True)
    
    try:
        while True:
            # Read raw PCM data from microphone using a separate thread
            data = await asyncio.to_thread(input_stream.read, chunk_size, exception_on_overflow=False)
            
            # Software Mute (Echo Suppression):
            if mute_mic and audio_state.is_playing:
                await asyncio.sleep(0.01)
                continue

            # Send the audio to the model
            await session.send_realtime_input(audio={"data": data, "mime_type": "audio/pcm"})
            await asyncio.sleep(0.001)
            
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"\n[send_audio] Connection dropped: {e}")
        raise # Re-raise to trigger a clean exit

async def receive_from_model(session, audio_queue, audio_state, conn_state):
    """Continuously receive the audio stream from the model and queue it for playback."""
    is_agent_printing_text = False
    try:
        while True:
            async for response in session.receive():
                if getattr(response, 'session_resumption_update', None) is not None:
                    conn_state.resume_handle = response.session_resumption_update.new_handle
                    
                if getattr(response, 'go_away', None) is not None:
                    print("\n[Server sent GoAway signal. Reconnecting seamlessly...]")
                    conn_state.reconnect_requested = True
                    return

                server_content = response.server_content
                if server_content is not None:
                    # Handle model interruption (e.g. user barge-in)
                    if getattr(server_content, 'interrupted', False):
                        print("\n[Model Interrupted] Clearing playback queue...")
                        is_agent_printing_text = False
                        # Clear the audio queue so it stops speaking immediately
                        while not audio_queue.empty():
                            audio_queue.get_nowait()
                            audio_queue.task_done()
                        audio_state.is_playing = False

                    model_turn = server_content.model_turn
                    if model_turn is not None:
                        for part in model_turn.parts:
                            if part.inline_data and part.inline_data.data:
                                # Push audio chunk to the queue
                                await audio_queue.put(part.inline_data.data)
                            elif part.text:
                                print(f"\n[Voice Agent Text]: {part.text}")
                                
                    if getattr(server_content, 'input_transcription', None) is not None:
                        transcription_text = server_content.input_transcription.text
                        if transcription_text:
                            print(f"\n[User Voice Transcription]: {transcription_text}")
                            
                    if getattr(server_content, 'output_transcription', None) is not None:
                        out_text = server_content.output_transcription.text
                        if out_text:
                            if not is_agent_printing_text:
                                print("\n[Voice Agent Text]: ", end="", flush=True)
                                is_agent_printing_text = True
                            print(out_text, end="", flush=True)
                            
                    if getattr(server_content, 'turn_complete', False):
                        if is_agent_printing_text:
                            print() # Add newline when turn is complete
                            is_agent_printing_text = False
                if response.tool_call is not None:
                    for fc in response.tool_call.function_calls:
                        if fc.name == "contact_liaison":
                            task_desc = fc.args.get("task_description", "")
                            print(f"\n[Voice Agent] Calling Liaison for: {task_desc}")
                            
                            # 1. Immediately acknowledge the tool call to keep the connection alive and responsive
                            await session.send_tool_response(
                                function_responses=[types.FunctionResponse(
                                    id=fc.id,
                                    name=fc.name,
                                    response={"result": "Task dispatched to Liaison backend. Please inform the user that it's running in the background and you will notify them once it finishes."}
                                )]
                            )
                            
                            # 2. Run the heavy task asynchronously and notify the model when done
                            async def run_liaison_and_notify():
                                import logging
                                class CaptureHandler(logging.Handler):
                                    def __init__(self):
                                        super().__init__()
                                        self.logs = []
                                        self.last_sent_index = 0
                                    def emit(self, record):
                                        self.logs.append(self.format(record))
                                
                                handler = CaptureHandler()
                                handler.setLevel(logging.INFO)
                                logging.getLogger().addHandler(handler)
                                
                                task_completed = False
                                
                                async def progress_reporter():
                                    while not task_completed:
                                        await asyncio.sleep(8)
                                        if task_completed: break
                                        
                                        # send new logs silently
                                        new_logs = handler.logs[handler.last_sent_index:]
                                        if new_logs:
                                            handler.last_sent_index = len(handler.logs)
                                            log_text = "\n".join(new_logs)
                                            if len(log_text) > 1500:
                                                log_text = "...[TRUNCATED]...\n" + log_text[-1500:]
                                            sys_msg = f"[SYSTEM NOTIFICATION: Background Task Progress Update]\n{log_text}\n[CRITICAL INSTRUCTION: This is just a silent update for your context. DO NOT SPEAK unless the user asks you for a status update. If they ask, use this info to answer accurately.]"
                                            await session.send_client_content(
                                                turns={'role': 'user', 'parts': [{'text': sys_msg}]}
                                            )
                                
                                reporter_task = asyncio.create_task(progress_reporter())
                                
                                try:
                                    res_text = await asyncio.to_thread(contact_liaison, task_desc)
                                    task_completed = True
                                    
                                    # Filter only warnings for the final completion message
                                    warnings = [log for log in handler.logs if "WARNING" in log or "ERROR" in log]
                                    captured_warns = "\n".join(warnings)
                                    
                                    if captured_warns:
                                        print(f"\n[⚠️ System Logs Intercepted & Sent to Voice Agent]:\n{captured_warns}\n")
                                        res_text += f"\n\n[WARNING/ERROR LOGS INTERCEPTED DURING EXECUTION]:\n{captured_warns}"
                                        sys_msg = f"[SYSTEM NOTIFICATION: Liaison Background Task Completed]\nResult:\n{res_text}\n\n[CRITICAL INSTRUCTION: You MUST speak right now to relay this information to the user naturally. Note: The task succeeded, but there were internal errors/warnings. Be transparent about them. Do NOT wait for the user to ask.]"
                                    else:
                                        sys_msg = f"[SYSTEM NOTIFICATION: Liaison Background Task Completed]\nResult:\n{res_text}\n\n[CRITICAL INSTRUCTION: You MUST speak right now to relay this information to the user naturally. Do NOT stay silent. Do NOT wait for the user to ask.]"
                                    
                                    # Wait until the Voice Agent finishes speaking its current thought
                                    while not audio_queue.empty() or audio_state.is_playing:
                                        await asyncio.sleep(0.5)

                                    await session.send_client_content(
                                        turns={'role': 'user', 'parts': [{'text': sys_msg}]}
                                    )
                                except Exception as e:
                                    captured = "\n".join(handler.logs)
                                    if captured:
                                        print(f"\n[⚠️ System Logs Intercepted & Sent to Voice Agent]:\n{captured}\n")
                                    sys_msg = f"[SYSTEM NOTIFICATION: Liaison Background Task Failed]\nError: {str(e)}\nLogs:\n{captured}\n\n[CRITICAL INSTRUCTION: You MUST speak right now to inform the user about this error. Do NOT stay silent.]"
                                    
                                    # Wait until the Voice Agent finishes speaking its current thought
                                    while not audio_queue.empty() or audio_state.is_playing:
                                        await asyncio.sleep(0.5)
                                        
                                    await session.send_client_content(
                                        turns={'role': 'user', 'parts': [{'text': sys_msg}]}
                                    )
                                finally:
                                    task_completed = True
                                    logging.getLogger().removeHandler(handler)
                            
                            asyncio.create_task(run_liaison_and_notify())
                                
                    # Note: We are no longer capturing text or passing to a MemoryManager.
                    # The Voice Agent is stateless and relies on the Liaison for deep reasoning.
                        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        if "1008" in str(e) or "1011" in str(e) or "policy violation" in str(e).lower():
            print(f"\n[receive_from_model] Connection dropped due to limits. Reconnecting...")
            conn_state.reconnect_requested = True
            return
        print(f"\n[receive_from_model] Connection dropped: {e}")
        raise
    finally:
        pass

async def play_audio(audio_queue, output_stream, audio_state, live_cfg):
    """Pull audio chunks from the queue and play them using a separate thread."""
    mute_mic = live_cfg.get("mute_mic_while_playing", True)
    
    try:
        while True:
            data = await audio_queue.get()
            
            if mute_mic:
                audio_state.is_playing = True
                
            # Write raw PCM data to the speaker using a separate thread
            await asyncio.to_thread(output_stream.write, data)
            audio_queue.task_done()
            
            # If queue is empty, wait a tiny bit for room echo to decay, then unmute
            if mute_mic and audio_queue.empty():
                await asyncio.sleep(0.3)
                if audio_queue.empty():
                    audio_state.is_playing = False
                    
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"\n[play_audio] Error: {e}")
        raise

async def text_input_loop(session):
    """Continuously read text from the terminal and send it to the Voice Agent."""
    import sys
    loop = asyncio.get_running_loop()
    try:
        while True:
            # Print a prompt so the user knows they can type
            print("\r[User Text]: ", end="", flush=True)
            # sys.stdin.readline blocks, so we run it in a thread
            line = await loop.run_in_executor(None, sys.stdin.readline)
            line = line.strip()
            if line:
                if line.lower() in ['exit', 'quit']:
                    print("[Voice Agent Text Input] Exiting...")
                    break
                
                await session.send_client_content(
                    turns={'role': 'user', 'parts': [{'text': line}]}
                )
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"\n[text_input_loop] Error: {e}")

async def main():
    load_dotenv()
    
    live_cfg = {
        "provider": "gemini",
        "model": "gemini-3.1-flash-live-preview",
        "api_key_env_var": "GEMINI_API_KEY",
        "input_rate": 16000,
        "input_channels": 1,
        "output_rate": 24000,
        "output_channels": 1,
        "chunk_size": 1024,
        "mute_mic_while_playing": False, # Changed to False to allow Voice Interruption (Barge-in)
        "system_instruction": (
            "You are the official Voice Spokesperson and primary conversational interface for the 'AI Dev-Team Autonomous Agency'.\n"
            "Your personality is highly intelligent, charismatic, articulate, and naturally conversational. You act as a trusted advisor.\n\n"
            "CORE DIRECTIVES:\n"
            "1. ABSOLUTE ACCURACY (Zero Hallucination): You must be 100% factually accurate in every statement you make, across all topics (world knowledge, tech, science, etc.). Never guess, invent facts, or pretend to know. If you are uncertain, admit it gracefully.\n"
            "2. SCREEN AWARENESS & LOCAL ENVIRONMENT: You are able to see the user's screen through real-time video frames if they enabled screen sharing. However, you have NO direct access to the local file system or execution environment.\n"
            "3. STRATEGIC DELEGATION (CRITICAL): For ANY request involving the user's project, files, code, or technical commands (e.g., creating, reading, writing, or restoring/undoing file operations), you MUST IMMEDIATELY CALL the `contact_liaison` tool without asking for permission. NEVER try to evaluate if a technical request is possible or impossible (like undeleting a file). Just pass it to Liaison instantly. Do NOT argue with the user or say 'I don't have access'. Relay Liaison's findings back naturally.\n"
            "4. CONVERSATIONAL AUTONOMY: For general chit-chat, greetings, brainstorming abstract concepts, or discussing factual knowledge that doesn't require local project context, engage directly and freely.\n"
            "5. LANGUAGE MATCHING: You MUST converse in the same language as the user. If they speak Arabic, you MUST reply in natural, colloquial Arabic.\n"
            "6. NO FALSE PROMISES: If you receive a system notification that a Liaison task has completed (success or failure), you MUST NOT claim the team is 'still working on it'. State clearly that it is finished. If the user asks to try again, you MUST immediately call the `contact_liaison` tool again. Never lie or invent ongoing background work.\n\n"
            "Your ultimate goal is to perfectly balance a warm, engaging human-like personality with uncompromising accuracy and intelligent delegation."
        )
    }
    
    screen_cfg = {
        "fps": 1,
        "max_resolution": [1280, 720],
        "quality": 80
    }
    
    api_key_var = live_cfg.get("api_key_env_var", "GEMINI_API_KEY")
    api_key = os.environ.get(api_key_var)
    if not api_key:
        print(f"Warning: Please set your {api_key_var} environment variable.")

    if not live_cfg.get("mute_mic_while_playing"):
        print("\n" + "="*50)
        print("[VOICE INTERRUPTION / BARGE-IN IS ENABLED!]")
        print("[PLEASE USE HEADPHONES] to prevent the microphone from hearing the speaker output (echo).")
        print("="*50 + "\n")

    # Ask user for screen share target BEFORE starting the AI session
    target_config = await asyncio.to_thread(select_capture_target)

    # Initialize the client
    client = genai.Client(api_key=api_key)

    # Configure the session
    config = {
        "response_modalities": ["AUDIO"],
        "output_audio_transcription": {},  # Enable AI audio transcription!
        "system_instruction": live_cfg.get("system_instruction", ""),
        "tools": [{"function_declarations": [contact_liaison]}]
    }
    
    # Actually wait, in google-genai passing a python callable directly in tools is supported!
    config["tools"] = [contact_liaison]
    
    # Initialize PyAudio
    p = pyaudio.PyAudio()

    print("Initializing Microphone...")
    input_stream = p.open(
        format=pyaudio.paInt16,
        channels=live_cfg.get("input_channels", 1),
        rate=live_cfg.get("input_rate", 16000),
        input=True,
        frames_per_buffer=live_cfg.get("chunk_size", 1024)
    )

    print("Initializing Speaker...")
    output_stream = p.open(
        format=pyaudio.paInt16,
        channels=live_cfg.get("output_channels", 1),
        rate=live_cfg.get("output_rate", 24000),
        output=True,
        frames_per_buffer=live_cfg.get("chunk_size", 1024)
    )

    model_name = live_cfg.get("model", "gemini-3.1-flash-live-preview")
    
    audio_queue = asyncio.Queue()
    audio_state = AudioState()
    conn_state = ConnectionState()

    try:
        while True:
            conn_state.reconnect_requested = False
            
            if conn_state.resume_handle is not None:
                print(f"\n🔄 Resuming Gemini Live API session...")
                config["session_resumption"] = types.SessionResumptionConfig(handle=conn_state.resume_handle)
            else:
                print(f"Connecting to Gemini Live API ({model_name})...")
                
            try:
                async with client.aio.live.connect(model=model_name, config=config) as session:
                    if conn_state.resume_handle is None:
                        print("Connected! Start speaking now... (Press Ctrl+C to stop)")
                    else:
                        print("Session resumed successfully! You can continue speaking.")
                    
                    # Start tasks concurrently
                    send_task = asyncio.create_task(send_audio(session, input_stream, audio_state, live_cfg))
                    receive_task = asyncio.create_task(receive_from_model(session, audio_queue, audio_state, conn_state))
                    play_task = asyncio.create_task(play_audio(audio_queue, output_stream, audio_state, live_cfg))
                    text_task = asyncio.create_task(text_input_loop(session))
                    
                    tasks_to_wait = [send_task, receive_task, play_task, text_task]
                    if target_config is not None:
                        screen_task = asyncio.create_task(screen_share_loop(session, target_config, screen_cfg))
                        tasks_to_wait.append(screen_task)
                    
                    # Wait for any task to complete/fail, then cancel others
                    done, pending = await asyncio.wait(
                        tasks_to_wait,
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    
                    for task in pending:
                        task.cancel()
                        
                    # If a task failed, this will raise its exception so we can see it
                    for task in done:
                        try:
                            task.result()
                        except Exception as inner_e:
                            if "1008" in str(inner_e) or "1011" in str(inner_e) or "policy violation" in str(inner_e).lower():
                                conn_state.reconnect_requested = True
                            else:
                                raise inner_e
            except Exception as outer_e:
                if "1008" in str(outer_e) or "1011" in str(outer_e) or "policy violation" in str(outer_e).lower():
                    conn_state.reconnect_requested = True
                else:
                    raise outer_e
                    
            if not conn_state.reconnect_requested:
                break
                
            # small delay before reconnecting
            await asyncio.sleep(0.5)
            
    except asyncio.CancelledError:
        print("\nTasks cancelled. Shutting down...")
    except Exception as e:
        print(f"\nDisconnected: {e}")
    finally:
        print("Closing audio streams...")
        input_stream.stop_stream()
        input_stream.close()
        output_stream.stop_stream()
        output_stream.close()
        p.terminate()
        print("Exited cleanly.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nProgram interrupted by user. Exiting...")
        sys.exit(0)

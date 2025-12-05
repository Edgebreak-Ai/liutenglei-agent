# -*- coding: utf-8 -*-
from listener import listen_for_wake_and_task
import time
import requests
from bs4 import BeautifulSoup
import ast
import inspect
import os
import re
import platform
from string import Template
from typing import List, Callable, Tuple
from contextlib import contextmanager  # <<< added
import threading

import speaker

from prompt_template import react_system_prompt_template
import tools

# New API endpoint
API_URL = "https://openrouter.ai/api/v1/chat/completions"


class ReActAgent:
    def __init__(self, tools: List[Callable], model: str):
        self.tools = {func.__name__: func for func in tools}
        self.model = model
        api_key = "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"
        self.headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        # Ensure there's always a valid project directory for tools that rely on it.
        # Default to the current working directory; callers may override this attribute.
        try:
            self.project_directory = os.getcwd()
        except Exception:
            # Fallback to the script directory if cwd is unavailable for some reason
            self.project_directory = os.path.dirname(os.path.abspath(__file__))
        # Speech manager state: thread and stop event used to cancel ongoing speech
        self._speak_thread = None
        self._speak_stop_event = None

    @contextmanager
    def _chdir_to_project(self):
        """Temporarily switch CWD to the project directory for tool execution."""
        prev = os.getcwd()
        try:
            os.makedirs(self.project_directory, exist_ok=True)
            os.chdir(self.project_directory)
            yield
        finally:
            os.chdir(prev)

    def time_now(self):
        local_time = time.localtime()
        return time.strftime("%Y-%m-%d %H:%M:%S", local_time)

    # -- Speech control -------------------------------------------------
    def _cancel_current_speak(self, timeout: float = 0.5):
        """Stop any currently playing speech. Returns after attempting to join the thread for `timeout` seconds."""
        try:
            if self._speak_stop_event is not None:
                self._speak_stop_event.set()
        except Exception:
            pass

        try:
            if self._speak_thread is not None and self._speak_thread.is_alive():
                self._speak_thread.join(timeout)
        except Exception:
            pass

        self._speak_thread = None
        self._speak_stop_event = None

    def _safe_speak(self, text: str, stop_event: threading.Event):
        """Safe wrapper for speaking that handles errors gracefully."""
        try:
            speaker.speak(text, stop_event)
            
        except Exception as e:
            print(f"⚠️ Speech error: {e}")


    # Update the _start_speak method:
    def _start_speak(self, text: str):

        # Cancel previous speech
        self._cancel_current_speak()


        stop_event = threading.Event()
        t = threading.Thread(
            target=self._safe_speak, 
            args=(text, stop_event), 
            daemon=True
        )
        self._speak_stop_event = stop_event
        self._speak_thread = t
        t.start()


    # ------------------------------------------------------------------

    def run(self, user_input: str):
        print(self.render_system_prompt(react_system_prompt_template))
        messages = [
            {"role": "user", "content": self.render_system_prompt(react_system_prompt_template)},
            {"role": "user", "content": f"{user_input}"}
        ]

        while True:
            content = self.call_model(messages)

            if "<final_answer>" in content:
                final_answer = re.search(r"<final_answer>(.*?)</final_answer>", content, re.DOTALL)
                answer_text = final_answer.group(1)
                # attempt to speak the final answer in background; ignore errors
                try:
                    self._start_speak(answer_text)
                except Exception as e:
                    print(f"⚠️ Speech start error: {e}")
                return answer_text

            action_match = re.search(r"<action>(.*?)</action>", content, re.DOTALL)
            if not action_match:
                # Fallback: if model didn't act, feed back an observation and continue
                observation = (
                    "Model did not return an <action>...</action> or <final_answer>...</final_answer>. "
                    "Please respond with a single tool call like run_py_code('...') or a <final_answer>."
                )
                print(f"\n\n🔍 Observation: {observation}")
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"<observation>{observation}</observation>"})
                continue

            action = action_match.group(1)

            # Robustly parse actions; feed errors back to the model instead of crashing
            try:
                tool_name, args = self.parse_action(action)
            except Exception as e:
                observation = (
                    f"Action parse error: {e}. "
                    "Return a plain Python function call expression like run_py_code('...'), "
                    "not a signature or prose. You returned: "
                    f"{action!r}"
                )
                print(f"\n\n🔍 Observation: {observation}")
                messages.append({"role": "assistant", "content": content})
                messages.append({"role": "user", "content": f"{observation}"})
                continue

            print(f"\n\n🔧 Action: {tool_name}({', '.join(map(str, args))})")
            should_continue = (
                input("\n\nAgent is running a potentially harmful command, continue? (Y/N)")
                if tool_name == "run_terminal_command" else "y"
            )
            if should_continue.lower() != 'y':
                print("\n\nOperation canceled by user.")
                return "Operation canceled by user"

            try:
                # Guard unknown tools
                if tool_name not in self.tools:
                    observation = (
                        f"Unknown tool: {tool_name}. "
                        f"Available tools: {', '.join(self.tools.keys())}"
                    )
                    print(f"\n\n🔍 Observation: executed with error")                    
                else:
                    # <<< the only behavioral change: force tools to run inside project_directory
                    with self._chdir_to_project():
                        observation = self.tools[tool_name](*args)
                        print(f"\n\n🔍 Observation: executed successfully")                        
            except Exception as e:
                observation = f"Tool executed with error: {str(e)}"
                print(f"\n\n🔍 Observation: executed with error")
    
            messages.append({"role": "assistant", "content": content})
            messages.append({"role": "user", "content": f"{observation}"})
    def get_tool_list(self) -> str:
        tool_descriptions = []
        for func in self.tools.values():
            name = func.__name__
            signature = str(inspect.signature(func))
            doc = inspect.getdoc(func) or ""
            tool_descriptions.append(f"- {name}{signature}: {doc}")
        return "\n".join(tool_descriptions)

    def render_system_prompt(self, system_prompt_template: str) -> str:
        """Render the system prompt template and replace variables."""
        tool_list = self.get_tool_list()
        try:
            file_list = ", ".join(
                os.path.abspath(os.path.join(self.project_directory, f))
                for f in os.listdir(self.project_directory)
            )
        except Exception:
            file_list = ""
        return Template(system_prompt_template).substitute(
            tool_list=tool_list,
            time_now=self.time_now(),
            fan_status=tools._get_fan_status(),
        )

    def call_model(self, messages):
        print("\n\nRequesting model, please wait...")
        payload = {
            "model": self.model,          # use model passed to ReActAgent
            "messages": messages, 
            "max_tokens":3000 
        }

        try:
            response = requests.post(API_URL, headers=self.headers, json=payload, timeout=(60,180))
        except requests.RequestException as e:
            raise Exception(f"Model request error: {e}")

        if response.status_code != 200:
            raise Exception(f"Model request failed: {response.text}")

        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, AttributeError):
            raise Exception(f"Unexpected response schema: {data}")

        if not content:
            raise Exception(f"Empty content in response: {data}")

        return content

    def parse_action(self, code_str: str) -> Tuple[str, List]:
        import ast as _ast
        import re as _re

        s = code_str.strip()

        # Strip code fences if present
        s = _re.sub(r"^```(?:\w+)?\n", "", s)
        s = _re.sub(r"\n```$", "", s)

        # Detect obvious signature/type-hint patterns and fail fast
        if _re.match(r'^\s*\w+\s*\([^)]*\)\s*->\s*[\w\[\], .]+$', s):
            raise ValueError("Got a function signature, not a call")

        # Auto-quote bare `.` or file paths without quotes
        s = _re.sub(r'=\s*(\.)($|[,)])', r'="."\2', s)  # e.g., path=. → path="."
        s = _re.sub(r'=\s*([A-Za-z0-9_\-/\\]+)($|[,)])', r'="\1"\2', s)  # quote barewords

        # Fix Windows-style backslashes in plain paths without disturbing
        # legitimate escape sequences (e.g. ``\n`` in content strings).
        def _fix_path(match):
            quote = match.group(1)
            inner = match.group(2)
            # Skip strings containing common escape sequences
            if any(seq in inner for seq in ("\\n", "\\r", "\\t", "\\'", '\\"')):
                return match.group(0)
            inner = inner.replace('\\\\', '\\').replace('\\', '/')
            return f"{quote}{inner}{quote}"

        s = _re.sub(r'(["\'])(.*?)(?<!\\)\1', _fix_path, s)

        try:
            expr = _ast.parse(s, mode='eval').body
        except SyntaxError as e:
            raise ValueError(f"Invalid syntax in action: {e}")

        if not isinstance(expr, _ast.Call):
            raise ValueError(f"Not a function call: {s!r}")

        if isinstance(expr.func, _ast.Name):
            func_name = expr.func.id
        else:
            raise ValueError(f"Unsupported function expression: {_ast.dump(expr.func)}")

        args: List = []
        for a in expr.args:
            if isinstance(a, _ast.Constant):
                args.append(a.value)
            else:
                args.append(_ast.get_source_segment(s, a).strip())

        for kw in expr.keywords:
            if isinstance(kw.value, _ast.Constant):
                args.append(f"{kw.arg}={kw.value!r}")
            else:
                args.append(f"{kw.arg}={_ast.get_source_segment(s, kw.value).strip()}")

        return func_name, args

    def _parse_single_arg(self, arg_str: str):
        """Parse a single argument."""
        arg_str = arg_str.strip()

        if (arg_str.startswith('"') and arg_str.endswith('"')) or \
           (arg_str.startswith("'") and arg_str.endswith("'")):
            inner_str = arg_str[1:-1]
            inner_str = inner_str.replace('\\"', '"').replace("\\'", "'")
            inner_str = inner_str.replace('\\n', '\n').replace('\\t', '\t')
            inner_str = inner_str.replace('\\r', '\r').replace('\\\\', '\\')
            return inner_str

        try:
            return ast.literal_eval(arg_str)
        except (SyntaxError, ValueError):
            return arg_str

    

def main():
    
    import inspect

    def discover_tools_from_module(mod):
        funcs = []
        for name, obj in inspect.getmembers(mod, inspect.isfunction):
            if not name.startswith("_"):
                funcs.append(obj)
        return funcs

    discovered_tools = discover_tools_from_module(tools)

    agent = ReActAgent(tools=discovered_tools, model="google/gemma-3n-e2b-it:free")
    while True:
        print("\n\n🛎️  Listening for wake word and task...")
        task = "turn off the fan"#listen_for_wake_and_task(timeout=None)
        print(f"\n\n📝 Task received: {task}")
        final_answer = agent.run(task)
        print(f"\n\n✅ Final Answer: {final_answer}")



if __name__ == "__main__":
    # Change this to your target project path
    main()

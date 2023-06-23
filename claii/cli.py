"""
Claii (Command Line AI Interface) CLI/REPL
"""
import os
import sys
import cmd
import subprocess
import sqlite3
from typing import Any
from collections import namedtuple

import click
import chromadb
from chromadb.config import Settings as ChromaSettings
import openai
import openai.error
from dotenv import load_dotenv

load_dotenv()
openai.api_key = os.getenv('OPENAI_API_KEY')

HOME_PATH = os.path.expanduser('~')
CLAI_SAVE_PATH = os.path.join(HOME_PATH, '.local', 'claii')
if not os.path.exists(CLAI_SAVE_PATH):
    os.makedirs(CLAI_SAVE_PATH)
SQLDB = sqlite3.connect(os.path.join(CLAI_SAVE_PATH, 'claii.db'))
chroma_setting = ChromaSettings(
    persist_directory=os.path.join(CLAI_SAVE_PATH, 'chroma')
)
CHROMA_CLIENT = chromadb.Client(chroma_setting)


def dict_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    return dict(zip(fields, row))


def namedtuple_factory(cursor, row):
    fields = [column[0] for column in cursor.description]
    cls = namedtuple('Row', fields)
    return cls._make(row)


SQLDB.row_factory = dict_factory


def get_history(sid):
    res = SQLDB.execute("""
        SELECT role, content FROM chat_messages WHERE sid = ? ORDER BY timestamp ASC
    """, (sid,))
    return list(res)


def save_history(sid, role, content):
    SQLDB.execute("""
        INSERT INTO chat_messages (sid, role, content) VALUES (?, ?, ?)
    """, (sid, role, content))
    SQLDB.commit()


def new_sid(title) -> int:
    sid = SQLDB.execute("""
        INSERT INTO chat_sessions (title, model, provider) VALUES (?, ?, ?)
    """, (title, 'gpt-3.5-turbo', 'openai'))
    SQLDB.commit()
    return sid.lastrowid


def set_session_title(sid, title) -> None:
    SQLDB.execute("""
        UPDATE chat_sessions SET title = ? WHERE id = ?
    """, (title, sid))
    SQLDB.commit()


def chat(prompt, sid=None) -> int:
    """
    Chat/Instruct with a user prompt
    Initially use openai.ChatCompletion
    """
    messages = []
    system_content = 'You are a helpful assistant.'
    if sid:
        res = SQLDB.execute("""
            SELECT title FROM chat_sessions WHERE id = ?
        """, (sid,))
        session = res.fetchone()
        if session['title'] == '':
            set_session_title(sid, prompt[:50])
        history = get_history(sid)
        for entry in history:
            messages.append(entry)
    else:
        sid = new_sid(prompt[:50])
        history = []
        messages.append({'role': 'system', 'content': system_content})

    messages.append({'role': 'user', 'content': prompt})
    save_history(sid, 'user', prompt)

    try:
        response = []
        res_stream = openai.ChatCompletion.create(
            model='gpt-3.5-turbo',
            messages=messages,
            stream=True,
        )
        for chunk in res_stream:
            content = chunk['choices'][0].get('delta', {}).get('content')
            if content:
                response.append(content)
                print(content, end='')
                sys.stdout.flush()
        print()
        save_history(sid, 'assistant', ''.join(response))
    except openai.error.OpenAIError as e:
        print(e)

    return sid


# TODO: set a short alias
def name(cmd_name):
    """Decorator to set the command name
    """
    assert cmd_name.startswith(':')

    def decorator(f):
        f.cmd_name = cmd_name
        return f
    return decorator


class ClaiRepl(cmd.Cmd):
    """
    REPL class, inherits from cmd.Cmd
    """
    prompt = '>>> '

    def __init__(self):
        super().__init__()
        self.real_commands = {}
        for fnname in dir(self):
            func = getattr(self, fnname)
            if hasattr(func, 'cmd_name'):
                self.real_commands[func.cmd_name] = func

        self.sid = None
        self.chroma_client = None
        self.setup_local_dbs()

    def setup_local_dbs(self) -> None:
        cursor = SQLDB.cursor()
        cursor.execute("""SELECT name FROM sqlite_master
                       WHERE type='table' AND name='chat_messages'""")
        if not cursor.fetchone():
            cursor.execute("""
                Create TABLE chat_sessions (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  title TEXT NOT NULL,
                  model TEXT NOT NULL,
                  provider TEXT NOT NULL,
                  updated DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            cursor.execute("""
               CREATE TABLE chat_messages (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sid integer NOT NULL references chat_sessions(id),
                  role TEXT NOT NULL,
                  content TEXT NOT NULL,
                  timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                );
            """)
            SQLDB.commit()

    def default(self, line) -> None:
        command, _, arg = line.partition(' ')
        if command in self.real_commands:
            try:
                self.real_commands[command](arg)
            except Exception as e:
                print(f'Error: {e}')
        else:
            self.sid = chat(line, self.sid)

    def emptyline(self):
        pass

    def completedefault(self, *ignored: Any) -> list[str]:
        return list(self.real_commands.keys())

    def do_help(self, arg):
        arg = arg.strip()
        if arg == '':
            print('available commands: ', end='')
            for cmdname in self.real_commands:
                print(f' {cmdname}', end='')
            print()
        elif arg in self.real_commands:
            print(self.real_commands[arg].__doc__)
        else:
            print(f'unknown command: {arg}')

    def do_shell(self, arg):
        """Run a shell command"""
        print('running shell command:', arg)
        subprocess.run(arg, shell=True, check=False)

    @name(':hello')
    def hello(self, arg):
        """Hello command"""
        print('Hello, ' + arg)

    @name(':quit')
    def quit(self, arg):
        """Exit the REPL"""
        return True

    @name(':ss')
    def list_sessions(self, arg):
        """list all chat sessions"""
        res = SQLDB.execute("""
            SELECT id, title, updated FROM chat_sessions ORDER BY updated ASC
        """)
        for row in res:
            print(f'{row["id"]}: {row["title"]} ({row["updated"]})')

    @name(':cs')
    def continue_session(self, arg):
        """continue a saved sessions"""
        try:
            sid = int(arg)
        except ValueError:
            print('please specify a session id')
            return

        res = SQLDB.execute('SELECT id FROM chat_sessions')
        ids = [row['id'] for row in res]
        if sid not in ids:
            print(f'unknown session id: {sid}')
        self.sid = sid

    @name(':sh')
    def session_history(self, arg):
        """show the history of a session"""
        if self.sid is None:
            print('no session selected')
            return

        res = SQLDB.execute("""
            SELECT role, content, timestamp FROM chat_messages
            WHERE sid = ? ORDER BY timestamp ASC
        """, (self.sid,))
        for row in res:
            print(f'{row["timestamp"]} {row["role"]}: {row["content"]}')

    @name(':sm')
    def system_message(self, arg):
        """set a system message"""
        self.sid = new_sid('')
        save_history(self.sid, 'system', arg)


@click.group(invoke_without_command=True)
@click.pass_context
def cli(ctx):
    if ctx.invoked_subcommand is None:
        ctx.invoke(repl)


@click.command()
def repl():
    ClaiRepl().cmdloop()

@click.command()
@click.argument('prompt')
def hello(prompt):
    click.echo('Hello, ' + prompt)

if __name__ == '__main__':
    cli()

import importlib
from pathlib import Path
from actions._base import Action

base_dir = "manager"
actions_dir = "actions"
actions_path = Path(base_dir) / actions_dir
actions = dict()
for filename in actions_path.glob("[!_]*"):
    action_module = importlib.import_module(f"{actions_dir}.{filename.stem}")
    actions[filename.stem] = action_module.action

# test run

actions_names = ["ping", "get", "put", "exploit"]

kwargs = {"id": "naliway", "script": "test.py", "srv": "test"}
answers = {"ping": "pong", "put": "123", "get":"321", "exploit": "1"}
extras = {"put": "test_321"}
for name in actions_names:
    print(f"action {name}")
    print("-->", actions[name](**kwargs).send(['test']))
    r = Action(
        1,
        "naliway",
        name,
        "test",
        answers.get(name),
        extras.get(name),
    )
    print("<-", actions[name].from_dict(kwargs).receive(r))

a = 1,2
def test(one, two):
    print(one, two)

test(a)
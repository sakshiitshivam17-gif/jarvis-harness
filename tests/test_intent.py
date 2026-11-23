import unittest

from jarvis import intent


class IntentTests(unittest.TestCase):
    def test_wake_removed(self):
        cleaned, found = intent.strip_wake("Jarvis, open Chrome")
        self.assertTrue(found)
        self.assertEqual(cleaned, "open chrome")

    def test_open_app(self):
        self.assertEqual(intent.parse("open chrome")["action"], "open")
        self.assertEqual(intent.parse("open chrome")["args"]["target"], "chrome")

    def test_open_url(self):
        parsed = intent.parse("open github.com")
        self.assertEqual(parsed["action"], "open_url")

    def test_search(self):
        parsed = intent.parse("search the web for quantum tunnelling")
        self.assertEqual(parsed["action"], "search")
        self.assertEqual(parsed["args"]["query"], "quantum tunnelling")

    def test_volume_set(self):
        parsed = intent.parse("set volume to 42")
        self.assertEqual(parsed["action"], "volume")
        self.assertEqual(parsed["args"], {"mode": "set", "value": 42})

    def test_volume_by_amount(self):
        parsed = intent.parse("increase volume by 15")
        self.assertEqual(parsed["args"]["mode"], "up")
        self.assertEqual(parsed["args"]["value"], 15)

    def test_brightness(self):
        self.assertEqual(intent.parse("brightness down")["args"]["mode"], "down")
        self.assertEqual(intent.parse("set brightness to 30")["args"]["value"], 30)

    def test_shutdown_and_lock(self):
        self.assertEqual(intent.parse("shut down")["action"], "shutdown")
        self.assertEqual(intent.parse("lock the screen")["action"], "lock")
        self.assertEqual(intent.parse("go to sleep")["action"], "standby")
        self.assertEqual(intent.parse("suspend")["action"], "suspend")

    def test_timer(self):
        parsed = intent.parse("set a timer for 5 minutes to stretch")
        self.assertEqual(parsed["action"], "timer")
        self.assertEqual(parsed["args"]["seconds"], 300)
        self.assertEqual(parsed["args"]["label"], "stretch")

    def test_note(self):
        parsed = intent.parse("remember that the drive is in drawer two")
        self.assertEqual(parsed["action"], "note")
        self.assertEqual(parsed["args"]["text"], "the drive is in drawer two")

    def test_calculate(self):
        parsed = intent.parse("calculate 12 times 8")
        self.assertEqual(parsed["action"], "calculate")
        self.assertEqual(parsed["args"]["expression"], "12 * 8")

    def test_weather_location(self):
        parsed = intent.parse("what's the weather in Mumbai")
        self.assertEqual(parsed["action"], "weather")
        self.assertEqual(parsed["args"]["location"], "mumbai")

    def test_shell(self):
        parsed = intent.parse("run command neofetch")
        self.assertEqual(parsed["action"], "shell")
        self.assertEqual(parsed["args"]["command"], "neofetch")

    def test_yes_no(self):
        self.assertEqual(intent.parse("yes")["action"], "confirm")
        self.assertEqual(intent.parse("nope")["action"], "cancel")

    def test_unknown(self):
        self.assertEqual(intent.parse("make me a sandwich")["action"], "unknown")

    def test_youtube_play(self):
        parsed = intent.parse("play believer on youtube")
        self.assertEqual(parsed["action"], "youtube")
        self.assertEqual(parsed["args"]["query"], "believer")
        self.assertEqual(intent.parse("play some lofi")["action"], "youtube")
        self.assertEqual(intent.parse("open youtube and play jazz")["action"], "youtube")

    def test_screen_vision(self):
        for phrase in ("look at my screen", "what's on my screen", "fix this error",
                       "review my code", "vibe coding", "open my screen"):
            self.assertEqual(intent.parse(phrase)["action"], "screen_look", phrase)

    def test_project_open(self):
        parsed = intent.parse("open project Harness 2.0")
        self.assertEqual(parsed["action"], "open")
        self.assertEqual(parsed["args"]["target"], "project harness 2.0")

    def test_agent_actions(self):
        self.assertEqual(intent.parse("click 7 in the calculator")["action"], "cua_task")
        self.assertEqual(intent.parse("type hello world")["action"], "cua_task")
        self.assertEqual(intent.parse("press ctrl+s")["action"], "cua_task")
        self.assertEqual(intent.parse("stop the agent")["action"], "cua_stop")
        self.assertEqual(
            intent.parse("go to github.com and search cua")["action"], "cua_task"
        )

    def test_agent_does_not_steal_plain_open(self):
        self.assertEqual(intent.parse("open chrome")["action"], "open")
        self.assertEqual(intent.parse("calculate 128 times 4")["action"], "calculate")

    def test_help_and_standby(self):
        self.assertEqual(intent.parse("what can you do")["action"], "help")
        self.assertEqual(intent.parse("stop listening")["action"], "standby")


if __name__ == "__main__":
    unittest.main()

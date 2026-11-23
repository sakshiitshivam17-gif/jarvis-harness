"""Fast local natural-language routing for voice commands.

The rule engine deliberately handles the high-frequency, latency-sensitive
commands. Anything it cannot place is passed to the optional neural core.
"""

from __future__ import annotations

import re

from . import config

FILLERS = re.compile(r"\b(?:please|kindly|for me|if you would|would you|could you|can you|zara|yaar|bhai|thoda|kripya|mera|meri|mere)\b")

DEVANAGARI = {
    "जार्विस": "jarvis", "सर": "sir", "खोलो": "kholo", "खोल": "khol", "बंद": "band",
    "करो": "karo", "कर": "kar", "दो": "do", "वॉल्यूम": "volume", "बढ़ाओ": "badhao",
    "बढ़ा": "badha", "घटाओ": "ghatao", "कम": "kam", "तेज": "tez", "स्क्रीन": "screen",
    "देखो": "dekho", "दिखाओ": "dikhao", "बताओ": "batao", "समय": "time", "कितने": "kitne",
    "बजे": "baje", "बैटरी": "battery", "कितनी": "kitni", "कितना": "kitna", "मौसम": "mausam",
    "टाइमर": "timer", "सेकंड": "second", "मिनट": "minute", "घंटे": "ghante",
    "लॉक": "lock", "सिस्टम": "system", "सो": "so", "जाओ": "jao", "चुप": "chup",
    "नमस्ते": "hello", "कृपया": "please", "म्यूजिक": "music", "गाना": "gaana",
    "चलाओ": "chalao", "बजाओ": "bajao", "स्क्रीनशॉट": "screenshot", "लो": "lo",
    "नोट": "note", "याद": "yaad", "रखो": "rakho", "पढ़ो": "padho", "क्या": "kya",
    "है": "hai", "हैं": "hain", "और": "aur", "को": "ko", "पर": "par", "में": "mein",
    "क्रोम": "chrome", "यूट्यूब": "youtube", "ब्राइटनेस": "brightness", "नोट्स": "notes",
    "शटडाउन": "shutdown", "रीस्टार्ट": "restart", "वाईफाई": "wifi", "वाई-फाई": "wifi",
    "ब्लूटूथ": "bluetooth", "प्ले": "play", "ओपन": "open", "सर्च": "search", "क्लोज": "close",
    "पीसी": "pc", "लैपटॉप": "laptop", "कैमरा": "camera", "फोटो": "photo", "कैप्चर": "capture",
    "मिनट": "minute", "मिनटों": "minutes", "सेकंड": "second", "सेकंडों": "seconds",
    "एक": "1", "दो": "2", "तीन": "3", "चार": "4", "पांच": "5", "पाँच": "5", "छह": "6",
    "सात": "7", "आठ": "8", "नौ": "9", "दस": "10", "बीस": "20", "तीस": "30",
    "चालीस": "40", "पचास": "50", "साठ": "60",
}
WAKE = re.compile(r"\b(?:hey\s+|ok(?:ay)?\s+)?(?:jarvis|jervis|jarvus|parvez|parvis|javis|jarvix|harvis|charvis|darvis|jarvez|जार्विस)\b", re.IGNORECASE)

YES = {"yes", "yeah", "yep", "yup", "sure", "confirm", "confirmed", "do it", "affirmative", "go ahead", "proceed", "make it so", "correct", "okay", "ok",
       "haan", "han", "ha", "bilkul", "theek hai", "thik hai", "karo", "kar do", "chalo"}
NO = {"no", "nope", "nah", "cancel", "abort", "negative", "not now", "stop", "hold on", "wait",
      "nahi", "na", "mat karo", "rehne do", "cancel karo"}


def strip_wake(text: str) -> tuple[str, bool]:
    found = bool(WAKE.search(text or ""))
    cleaned = WAKE.sub(" ", text or "")
    return normalise(cleaned), found


def normalise(text: str) -> str:
    text = (text or "").strip().lower()
    for dev, latin in DEVANAGARI.items():
        text = text.replace(dev, latin)
    text = text.replace("’", "'").replace("“", '"').replace("”", '"')
    text = FILLERS.sub(" ", text)
    text = re.sub(r"[,\s]+", " ", text)
    text = re.sub(r"^[\-–—\s]+|[\-–—\s]+$", "", text)
    text = text.strip(" .!?")
    return text


def intent(action: str, args: dict | None = None) -> dict:
    return {"action": action, "args": args or {}}


def _duration(text: str) -> int | None:
    total = 0
    found = False
    for match in re.finditer(r"(\d+)\s*(hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b", text):
        value = int(match.group(1))
        unit = match.group(2)[0]
        total += value * (3600 if unit == "h" else 60 if unit == "m" else 1)
        found = True
    if found and 0 < total <= 86400:
        return total
    return None


def _number(text: str) -> int | None:
    words = {
        "zero": 0, "ten": 10, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
        "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100,
        "half": 50, "max": 100, "full": 100,
    }
    match = re.search(r"\b(\d{1,3})\b", text)
    if match:
        return max(0, min(100, int(match.group(1))))
    for word, value in words.items():
        if re.search(rf"\b{word}\b", text):
            return value
    return None


def parse(text: str) -> dict:
    t = normalise(text)
    t = normalise(WAKE.sub(" ", t))
    if not t:
        return intent("empty")

    if t in YES:
        return intent("confirm")
    if t in NO:
        return intent("cancel")

    # --- Hinglish routing (Roman-script Hindi-English) ---------------------
    if re.fullmatch(r"(?:kya haal(?: hai)?|kaise ho|kaisa hai|sab theek)", t):
        return intent("wellbeing")
    if re.fullmatch(r"(?:kya kar sakte ho|madad|help chahiye|commands batao|kya kar sakta hai)", t):
        return intent("help")
    if re.fullmatch(r"(?:chup(?: ho jao)?|bas karo|shant|awaaz band karo)", t):
        return intent("quiet")
    if re.fullmatch(r"(?:so jao|standby|ruko|ruk jao|bas|dismiss)", t):
        return intent("standby")
    if re.fullmatch(r"(?:utho|jaag jao|wake up|wapas aao)", t):
        return intent("wake")
    if re.search(r"\b(?:kitne baje|time kya|samay kya|time batao)\b", t):
        return intent("time")
    if re.search(r"\b(?:aaj ki date|date kya|tarikh|aaj kaunsa din)\b", t):
        return intent("date")
    if re.search(r"\b(?:mausam|weather batao|garmi|sardi)\b", t):
        match = re.search(r"\b(?:mausam|weather)\s+(?:in|at|mein)\s+([a-z .'-]+)$", t)
        return intent("weather", {"location": (match.group(1).strip() if match else "")})
    if re.search(r"\b(?:battery|charge)\b.*\b(?:kitni|kitna|status|batao|hai)\b", t):
        return intent("system_metric", {"metric": "battery"})
    if re.search(r"\bcpu\b.*\b(?:kitna|usage|load|batao|hai)\b", t):
        return intent("system_metric", {"metric": "cpu"})
    if re.search(r"\b(?:ram|memory)\b.*\b(?:kitni|kitna|usage|batao|hai)\b", t):
        return intent("system_metric", {"metric": "memory"})
    if re.search(r"\b(?:disk|storage)\b.*\b(?:kitni|kitna|space|batao|hai)\b", t):
        return intent("system_metric", {"metric": "disk"})
    if re.search(r"\b(?:system status|status batao|haal batao|system kaisa|diagnostics)\b", t):
        return intent("status")
    if re.search(r"\b(?:screen|screen pe|screen par)\b.*\b(?:dekho|dikhao|batao|kya|check|padho)\b", t):
        return intent("screen_look")
    if re.search(r"\b(?:code|error|bug|terminal)\b.*\b(?:fix|check|dekho|batao|solve|thik)\b", t):
        return intent("screen_look")
    if re.search(r"\b(?:is error|yeh error|ye error)\b", t):
        return intent("screen_look")
    if re.search(r"\b(?:screenshot|screen shot)\b.*\b(?:lo|le|karo|banao|khinch)\b", t):
        return intent("screenshot")
    if re.search(r"\b(?:volume|sound|awaaz)\b", t):
        if re.search(r"\b(?:mute|band|off)\b", t):
            return intent("volume", {"mode": "mute"})
        if re.search(r"\b(?:unmute|on)\b", t):
            return intent("volume", {"mode": "unmute"})
        by = re.search(r"\bby\s+(\d{1,3})\b", t)
        if by and re.search(r"\b(?:badhao|badha|tez|up|increase|louder)\b", t):
            return intent("volume", {"mode": "up", "value": int(by.group(1))})
        if by and re.search(r"\b(?:ghatao|ghata|kam|dheema|down|decrease|quieter|lower|reduce)\b", t):
            return intent("volume", {"mode": "down", "value": int(by.group(1))})
        match = re.search(r"\b(?:volume|sound|awaaz)\b.*?(\d{1,3})\b", t)
        if match:
            return intent("volume", {"mode": "set", "value": max(0, min(100, int(match.group(1))))})
        if re.search(r"\b(?:badhao|badha|tez|up|increase|louder)\b", t):
            return intent("volume", {"mode": "up", "value": 10})
        if re.search(r"\b(?:ghatao|ghata|kam|dheema|down|decrease|quieter|lower|reduce)\b", t):
            return intent("volume", {"mode": "down", "value": 10})
        return intent("volume", {"mode": "status"})
    if re.search(r"\bbrightness\b", t):
        match = re.search(r"\b(\d{1,3})\b", t)
        if match:
            return intent("brightness", {"mode": "set", "value": max(5, min(100, int(match.group(1))))})
        if re.search(r"\b(?:badhao|badha|tez|up|increase)\b", t):
            return intent("brightness", {"mode": "up", "value": 10})
        if re.search(r"\b(?:ghatao|ghata|kam|dheema|down|decrease)\b", t):
            return intent("brightness", {"mode": "down", "value": 10})
        return intent("brightness", {"mode": "status"})
    if re.search(r"\b(?:lock karo|screen lock|lock kar do)\b", t):
        return intent("lock")
    if re.search(r"\b(?:restart karo|reboot karo|restart kar do)\b", t):
        return intent("restart")
    if re.search(r"\b(?:pc band|system band|laptop band|shutdown karo|shut down karo|power off karo)\b", t):
        return intent("shutdown")
    if re.search(r"\b(?:system so jao|laptop so jao|suspend karo|sleep mode)\b", t):
        return intent("suspend")
    if re.search(r"\b(?:wifi|wi-fi)\b", t):
        if re.search(r"\b(?:band|off|disable)\b", t):
            return intent("wifi", {"state": "off"})
        if re.search(r"\b(?:chalu|on|enable)\b", t):
            return intent("wifi", {"state": "on"})
        return intent("wifi", {"state": "status"})
    if re.search(r"\b(?:bluetooth)\b", t):
        if re.search(r"\b(?:band|off|disable)\b", t):
            return intent("bluetooth", {"state": "off"})
        if re.search(r"\b(?:chalu|on|enable)\b", t):
            return intent("bluetooth", {"state": "on"})
        return intent("bluetooth", {"state": "status"})
    if re.search(r"\b(?:do not disturb|dnd|disturb mat karo|notifications band)\b", t):
        return intent("dnd", {"state": "on"})
    if re.search(r"\b(?:timer|reminder)\b", t):
        seconds = _duration(t)
        if seconds:
            match = re.search(r"\b(?:to|ke liye)\s+(.+)$", t)
            label = match.group(1).strip() if match else ""
            return intent("timer", {"seconds": seconds, "label": label})
        return intent("timer_status")
    if re.search(r"\b(?:yaad rakho|note kar lo|note kar|note banao)\b", t):
        match = re.search(r"\b(?:yaad rakho|note kar lo|note kar|note banao)\s+(.+)$", t)
        if match:
            return intent("note", {"text": match.group(1).strip()})
    if re.search(r"\b(?:notes? (?:padho|sunao|batao)|notes? kya hain|mere notes)\b", t):
        return intent("read_notes")
    if re.search(r"\b(?:search karo|google karo|dhundo|dhoondo)\b", t):
        match = re.search(r"\b(?:search karo|google karo|dhundo|dhoondo)\s+(.+)$", t)
        query = match.group(1).strip() if match else re.sub(r"\b(?:search karo|google karo|dhundo|dhoondo)\b", "", t).strip()
        if query:
            return intent("search", {"query": query})
    match = re.search(r"^(?:youtube|yt)\s+(?:pe|par|mein)\s+(.+?)\s+(?:chalao|bajao|play karo)$", t)
    if match:
        return intent("youtube", {"query": match.group(1).strip()})
    match = re.match(r"^(.+?)\s+(?:chalao|bajao|play karo)$", t)
    if match and not re.search(r"\b(?:music|gaana|gana|song)\b", match.group(1)):
        return intent("youtube", {"query": match.group(1).strip()})
    if re.fullmatch(r"(?:music chalao|gaana chalao|gana bajao|music bajao|gaana bajao)", t):
        return intent("music")
    if re.fullmatch(r"(?:pause karo|roko|gaana roko|music pause)", t):
        return intent("media", {"mode": "pause"})
    if re.fullmatch(r"(?:resume karo|chalu karo|continue karo|gaana chalao dobara)", t):
        return intent("media", {"mode": "play"})
    if re.fullmatch(r"(?:next karo|agla gaana|agla track|skip karo)", t):
        return intent("media", {"mode": "next"})
    if re.fullmatch(r"(?:previous karo|pichla gaana|pichla track|peeche karo)", t):
        return intent("media", {"mode": "previous"})
    if re.search(r"\b(?:calculate karo|hisab karo)\b", t):
        expression = re.sub(r"\b(?:calculate karo|hisab karo)\b", "", t).strip()
        expression = expression.replace("plus", "+").replace("minus", "-").replace("into", "*").replace("times", "*").replace("divided by", "/")
        return intent("calculate", {"expression": expression})
    if re.search(r"\b(?:kholo|khol do|kholiye|open karo)\b", t):
        match = re.match(r"^(.+?)\s+(?:kholo|khol do|kholiye|open karo)$", t)
        target = match.group(1).strip() if match else re.sub(r"\b(?:kholo|khol do|kholiye|open karo)\b", "", t).strip()
        if target:
            if re.search(r"\.(com|org|net|io|dev|ai|co|in)(?:/|$)", target):
                return intent("open_url", {"url": target if target.startswith("http") else f"https://{target}", "label": target})
            return intent("open", {"target": target})
    match = re.match(r"^(.+?)\s+(?:band karo|band kar do|close karo|quit karo)$", t)
    if match:
        target = match.group(1).strip()
        if re.search(r"\b(?:pc|system|laptop|computer)\b", target):
            return intent("shutdown")
        return intent("close_app", {"app": target})
    if re.search(r"\bbattery\b", t):
        return intent("system_metric", {"metric": "battery"})


    # --- personality and housekeeping -------------------------------------
    if re.fullmatch(r"(hi|hello|hey|yo|good morning|good afternoon|good evening|greetings)", t):
        return intent("greet")
    if re.search(r"\b(thank you|thanks|thankyou|cheers|good job|well done|nice work)\b", t):
        return intent("thanks")
    if re.search(r"\b(who are you|what are you|your name|introduce yourself|what should i call you)\b", t):
        return intent("identity")
    if re.search(r"\b(help|what can you do|what can do|what do|list commands|show commands|command list|capabilities)\b", t) \
            and not re.search(r"\b(code|error|bug|screen|this|project)\b", t):
        return intent("help")
    if re.fullmatch(r"(stop listening|standby|stand down|go to sleep|sleep mode|that's all|thats all|dismissed|goodbye|good night)", t):
        return intent("standby")
    if re.fullmatch(r"(wake up|wake|are you there|you there|hello jarvis|come back)", t):
        return intent("wake")
    if re.fullmatch(r"(quiet|silence|shut up|stop talking|enough|hush|mute yourself)", t):
        return intent("quiet")
    if re.fullmatch(r"(clear|clear screen|clear feed|clear the screen|wipe the feed)", t):
        return intent("clear_feed")

    # --- time, date, status ------------------------------------------------
    if re.search(r"\b(what(?:'s| is)? the time|current time|time is it|tell me the time|what time)\b", t):
        return intent("time")
    if re.search(r"\b(what(?:'s| is)? the date|today'?s date|what day is it|date today|current date)\b", t):
        return intent("date")
    if re.search(r"\b(weather|temperature outside|forecast|raining|rain today|how hot|how cold)\b", t):
        match = re.search(r"\b(?:weather|forecast|temperature)\s+(?:in|at|for)\s+([a-z .'-]+)$", t)
        return intent("weather", {"location": (match.group(1).strip() if match else "")})
    if re.search(r"\b(full status|system status|status report|systems check|diagnostics|all systems|how are the systems)\b", t):
        return intent("status")
    if re.search(r"\b(how are you|how's it going|how are things)\b", t):
        return intent("wellbeing")
    for metric, patterns in {
        "cpu": r"\b(cpu|processor|processing load)\b",
        "memory": r"\b(memory|ram)\b",
        "disk": r"\b(disk|storage|hard drive space|ssd space)\b",
        "battery": r"\b(battery|charge level|power level)\b",
        "temperature": r"\b(temperature|thermals|how hot is the pc|cpu temp)\b",
        "network": r"\b(ip address|network status|internet status|connection status|what'?s my ip)\b",
        "volume": r"\b(volume|how loud)\b",
        "uptime": r"\b(uptime|how long have you been running)\b",
    }.items():
        if re.search(patterns, t) and re.search(r"\b(what|how|show|check|read|status|current|usage)\b", t):
            return intent("system_metric", {"metric": metric})
    if re.search(r"\b(what(?:'s| is) playing|now playing|which song|what song)\b", t):
        return intent("now_playing")

    # --- computer-use agent (CUA) -----------------------------------------
    if re.fullmatch(r"(?:stop|abort|cancel) (?:the |it |that )?(?:agent|automation|task|kaam)", t):
        return intent("cua_stop")
    if re.fullmatch(r"(?:stop|abort) it", t):
        return intent("cua_stop")
    match = re.match(r"^(?:use the computer to|automate|do this on screen:|agent[:,]?)\s+(.+)$", t)
    if match:
        return intent("cua_task", {"task": match.group(1).strip()})
    if re.match(r"^(?:click|double ?click|right ?click|type|press|scroll|select|fill|drag|clear|focus|toggle|check|uncheck|switch to)\b", t):
        return intent("cua_task", {"task": t})
    if " then " in t and (re.match(r"^(?:open|go|visit|clear|click|type|press|search|fill)\b", t)
                          or re.match(r"^open\s+\S+\s+then\s+(?:click|type|press|search|go|select)\b", t)):
        return intent("cua_task", {"task": t})
    if re.search(r"\b(?:calculator|browser|the app|the page|the window|the tab|text box|search box)\b", t) \
            and re.search(r"\b(?:click|type|press|enter|fill|select|scroll|clear)\b", t):
        return intent("cua_task", {"task": t})
    if re.match(r"^(?:go to|navigate to)\s+\S+\s+and\s+", t):
        return intent("cua_task", {"task": t})
    if re.search(r"\b(?:in the app|on the page|in the window)\b", t):
        return intent("cua_task", {"task": t})

    # --- apps, sites, files ------------------------------------------------
    if re.fullmatch(r"(open (?:my )?(?:downloads|documents|pictures|music|videos|home|desktop)|show (?:my )?files|file manager)", t):
        path = {
            "downloads": "~/Downloads", "documents": "~/Documents", "pictures": "~/Pictures",
            "music": "~/Music", "videos": "~/Videos", "home": "~", "desktop": "~/Desktop",
        }
        key = next((k for k in path if re.search(rf"\b{k}\b", t)), "home")
        return intent("open_path", {"path": path[key]})
    if re.fullmatch(r"(open )?(the )?(files|file manager|nautilus|explorer)", t):
        return intent("open_app", {"app": "files"})
    if re.fullmatch(r"(?:open|show) (?:my |the )?screen", t):
        return intent("screen_look")

    match = re.match(r"^open\s+(?:youtube|yt)\s+(?:and\s+)?(?:play|put on)\s+(.+)$", t)
    if match:
        return intent("youtube", {"query": match.group(1).strip()})
    match = re.match(r"^(?:open|launch|start|bring up|pull up)\s+(?:the\s+|my\s+)?(.+)$", t)
    if match:
        target = match.group(1).strip()
        if re.search(r"\.(com|org|net|io|dev|ai|co|in|gov|edu)(?:/|$)", target):
            return intent("open_url", {"url": target if target.startswith("http") else f"https://{target}", "label": target})
        if target.startswith(("~", "/")):
            return intent("open_path", {"path": target})
        return intent("open", {"target": target})

    match = re.match(r"^(?:close|quit|kill|exit|stop)\s+(?:the\s+|my\s+)?(.+)$", t)
    if match and not re.fullmatch(r"(stop|wait|now)", match.group(1)):
        return intent("close_app", {"app": match.group(1).strip()})

    # --- search ------------------------------------------------------------
    match = re.search(r"^(?:search(?: the web)?(?: for)?|google|look up|find)\s+(.+)$", t)
    if match:
        return intent("search", {"query": match.group(1).strip()})
    match = re.search(r"^(?:play|search)\s+(.+?)\s+on\s+(?:youtube|yt)$", t)
    if match:
        return intent("youtube", {"query": match.group(1).strip()})
    match = re.match(r"^open\s+(?:youtube|yt)\s+(?:and\s+)?(?:play|put on)\s+(.+)$", t)
    if match:
        return intent("youtube", {"query": match.group(1).strip()})
    match = re.match(r"^(?:youtube|you tube)\s+(.+)$", t)
    if match:
        return intent("youtube", {"query": match.group(1).strip()})
    if re.fullmatch(r"(play some music|play music|put on some music|music on)", t):
        return intent("music")
    match = re.match(r"^(?:play|put on)\s+(.+)$", t)
    if match and not re.search(r"\b(track|song|previous|next|music)\b", match.group(1)):
        return intent("youtube", {"query": match.group(1).strip()})

    # --- volume ------------------------------------------------------------
    if re.fullmatch(r"(mute|mute audio|mute the volume|silence the audio)", t):
        return intent("volume", {"mode": "mute"})
    if re.fullmatch(r"(unmute|unmute audio|restore audio|restore volume)", t):
        return intent("volume", {"mode": "unmute"})
    if re.search(r"\b(volume|sound|audio)\b", t) or re.fullmatch(r"(louder|quieter|turn it up|turn it down)", t):
        if re.search(r"\b(max|maximum|full)\b", t):
            return intent("volume", {"mode": "set", "value": 100})
        if re.search(r"\bhalf\b", t):
            return intent("volume", {"mode": "set", "value": 50})
        match = re.search(r"\b(?:volume|sound|audio)(?:\s+(?:to|at))?\s+(\d{1,3})\b", t)
        if match:
            return intent("volume", {"mode": "set", "value": max(0, min(100, int(match.group(1))))})
        by = re.search(r"\bby\s+(\d{1,3})\b", t)
        if re.search(r"\b(up|louder|raise|increase|boost)\b", t):
            amount = int(by.group(1)) if by else (25 if re.search(r"\b(a lot|lot|much)\b", t) else 10)
            return intent("volume", {"mode": "up", "value": max(1, min(100, amount))})
        if re.search(r"\b(down|quieter|lower|decrease|reduce)\b", t):
            amount = int(by.group(1)) if by else (25 if re.search(r"\b(a lot|lot|much)\b", t) else 10)
            return intent("volume", {"mode": "down", "value": max(1, min(100, amount))})
        return intent("volume", {"mode": "status"})

    # --- brightness --------------------------------------------------------
    if re.search(r"\bbrightness\b|\bscreen (?:dimmer|brighter|darker)\b", t) or re.fullmatch(r"(brighter|dimmer|darker)", t):
        value = _number(t)
        if value is not None:
            return intent("brightness", {"mode": "set", "value": value})
        if re.search(r"\b(up|brighter|raise|increase)\b", t):
            return intent("brightness", {"mode": "up", "value": 10})
        if re.search(r"\b(down|dimmer|darker|lower|decrease|reduce)\b", t):
            return intent("brightness", {"mode": "down", "value": 10})
        return intent("brightness", {"mode": "status"})

    # --- media -------------------------------------------------------------
    if re.fullmatch(r"(pause|pause music|pause the music|hold)", t):
        return intent("media", {"mode": "pause"})
    if re.fullmatch(r"(resume|resume music|continue|continue music|play)", t):
        return intent("media", {"mode": "play"})
    if re.fullmatch(r"(next|next track|skip|skip song|skip track)", t):
        return intent("media", {"mode": "next"})
    if re.fullmatch(r"(previous|previous track|last track|go back a track|back)", t):
        return intent("media", {"mode": "previous"})
    if re.fullmatch(r"(stop music|stop the music|stop playback)", t):
        return intent("media", {"mode": "stop"})

    # --- timers and notes --------------------------------------------------
    if re.search(r"\b(?:timer|remind me|reminder|alarm)\b", t):
        seconds = _duration(t)
        if seconds:
            match = re.search(r"\b(?:to|that)\s+(.+)$", t)
            label = match.group(1).strip() if match else ""
            return intent("timer", {"seconds": seconds, "label": label})
        return intent("timer_status")
    if re.search(r"\b(?:remember|note|jot down|write down|make a note)\b", t):
        match = re.search(r"\b(?:remember(?: that)?|note(?: that)?|jot down|write down|make a note(?: that)?)\s+(.+)$", t)
        if match:
            return intent("note", {"text": match.group(1).strip()})
    if re.search(r"\b(read (?:my )?notes|what did i note|show (?:my )?notes|notes)\b", t):
        return intent("read_notes")
    if re.search(r"\b(clear (?:my )?notes|delete (?:all )?notes|forget my notes)\b", t):
        return intent("clear_notes")

    # --- screen vision / coding help --------------------------------------
    if re.fullmatch(r"(?:open|show) (?:my |the )?screen", t):
        return intent("screen_look")
    if re.search(r"\b(?:look at|see|read|check|scan|analy[sz]e|what(?:'s| is) on)\b.*\bscreen\b", t):
        return intent("screen_look")
    if re.search(r"\b(?:fix|debug|review|explain|solve|help(?: me)?(?: with)?)\b.*\b(?:code|error|bug|stack ?trace|terminal|this|it)\b", t):
        return intent("screen_look")
    if re.search(r"\bwhat(?:'s| is) wrong with (?:this|my|the) (?:code|error|bug|project)\b", t):
        return intent("screen_look")
    if re.search(r"\b(?:help me (?:code|build|debug|with this|with my code)|vibe cod(?:e|ing))\b", t):
        return intent("screen_look")

    # --- machine control ---------------------------------------------------
    if re.search(r"\b(shut ?down|power off|turn off the (?:pc|computer|system)|switch off)\b", t):
        return intent("shutdown")
    if re.search(r"\b(restart|reboot|restart the (?:pc|computer|system))\b", t):
        return intent("restart")
    if re.search(r"\b(suspend|hibernate|put the (?:pc|computer|system) to sleep)\b", t):
        return intent("suspend")
    if re.search(r"\b(lock (?:the )?(?:screen|pc|computer|system|it)|lock screen)\b", t):
        return intent("lock")
    if re.search(r"\b(log out|sign out|logout)\b", t):
        return intent("logout")
    if re.fullmatch(r"(take a screenshot|screenshot|capture the screen|capture screen)", t):
        return intent("screenshot")
    if re.search(r"\b(empty (?:the )?trash|empty rubbish|clear trash)\b", t):
        return intent("empty_trash")
    if re.search(r"\b(open|show) (?:the )?(?:system )?monitor\b", t):
        return intent("open_app", {"app": "monitor"})

    # --- radios and presence ----------------------------------------------
    if re.search(r"\b(wifi|wi-fi|wireless)\b", t):
        if re.search(r"\b(off|disable|turn off|switch off|kill)\b", t):
            return intent("wifi", {"state": "off"})
        if re.search(r"\b(on|enable|turn on|switch on)\b", t):
            return intent("wifi", {"state": "on"})
        return intent("wifi", {"state": "status"})
    if re.search(r"\b(bluetooth)\b", t):
        if re.search(r"\b(off|disable|turn off|switch off)\b", t):
            return intent("bluetooth", {"state": "off"})
        if re.search(r"\b(on|enable|turn on|switch on)\b", t):
            return intent("bluetooth", {"state": "on"})
        return intent("bluetooth", {"state": "status"})
    if re.search(r"\b(do not disturb|dnd|silence notifications|mute notifications)\b", t):
        return intent("dnd", {"state": "on"})
    if re.search(r"\b(turn off do not disturb|disable do not disturb|allow notifications|notifications on)\b", t):
        return intent("dnd", {"state": "off"})
    if re.search(r"\b(night light|warm screen|blue light)\b", t):
        return intent("night_light", {"state": "off" if re.search(r"\b(off|disable|turn off)\b", t) else "on"})

    # --- math and shell ----------------------------------------------------
    if re.match(r"^(calculate|what is|what's|how much is)\b", t) and re.search(r"[0-9]|plus|minus|times|divided|over|multiplied", t):
        expression = re.sub(r"^(calculate|what is|what's|how much is)\s+", "", t)
        expression = expression.replace("plus", "+").replace("minus", "-").replace("times", "*").replace("multiplied by", "*").replace("divided by", "/").replace("over", "/").replace("x", "*")
        return intent("calculate", {"expression": expression})
    match = re.match(r"^(?:run command|execute command|shell|run|execute)\s+(.+)$", t)
    if match:
        return intent("shell", {"command": match.group(1).strip()})

    return intent("unknown")


HELP_SECTIONS = [
    ("APPS & WEB", ["open chrome", "open terminal", "open youtube", "search the web for quantum physics", "play lo-fi beats on youtube", "close spotify"]),
    ("SYSTEM", ["volume up", "set volume to 40", "mute", "lock the screen", "battery status", "what's my CPU usage", "take a screenshot"]),
    ("TIME & UTILITY", ["set a timer for five minutes", "remember that the backup drive is in drawer two", "read my notes", "what's the weather in Mumbai", "calculate 128 times 4"]),
    ("MACHINE", ["suspend", "restart", "shut down", "turn off wifi", "do not disturb", "run command neofetch"]),
    ("SCREEN & CODE", ["look at my screen", "what's on my screen", "fix this error", "review my code", "vibe coding"]),
    ("AGENT (ACTS FOR YOU)", ["click 7 in the calculator", "type hello in the search box", "press ctrl+s", "go to github.com and search cua", "stop the agent"]),
    ("VOICE", ["Jarvis, wake up", "quiet", "stop listening"]),
    ("HINGLISH", ["chrome kholo", "volume badha do", "screen dekho", "battery kitni hai", "pc band karo"]),
]

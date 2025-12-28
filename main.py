from fasthtml.common import *
from monsterui.all import *
from datetime import datetime, timedelta
import random
import json
import os
from pathlib import Path

# Import word lists
from words import ONE_BEE, TWO_BEE, THREE_BEE

# Database setup
db = database("spelling_bee.db")

users = db.t.users
if users not in db.t:
    users.create(id=int, username=str, is_guest=bool, created_at=str, pk="id")
    users.insert(username="Kira", is_guest=False, created_at=datetime.now().isoformat())
    users.insert(username="Sage", is_guest=False, created_at=datetime.now().isoformat())
    users.insert(username="Test", is_guest=False, created_at=datetime.now().isoformat())

words = db.t.words
if words not in db.t:
    words.create(
        id=int,
        word=str,
        difficulty_level=int,
        definition=str,
        functional_label=str,
        pronunciation=str,
        has_audio=bool,
        audio_url=str,
        audio_file_local=str,
        is_inflection=bool,
        base_word=str,
        is_primary=bool,
        primary_word=str,
        pk="id",
    )

user_word_progress = db.t.user_word_progress
if user_word_progress not in db.t:
    user_word_progress.create(
        id=int,
        user_id=int,
        word_id=int,
        times_attempted=int,
        times_correct=int,
        times_incorrect=int,
        first_attempted_at=str,
        last_attempted_at=str,
        next_review_at=str,
        current_streak=int,
        mastery_level=int,
        pk="id",
        foreign_keys=[("user_id", "users"), ("word_id", "words")],
    )

Users, Words, UserProgress = (
    users.dataclass(),
    words.dataclass(),
    user_word_progress.dataclass(),
)


def flatten_word_list(word_list):
    """Flatten word list handling alternate spellings"""
    flattened = []
    for item in word_list:
        if isinstance(item, list):
            # First item is primary, rest are alternates
            primary = item[0]
            alternates = item[1:] if len(item) > 1 else []
            flattened.append(
                {"word": primary, "alternates": alternates, "is_primary": True}
            )
            for alt in alternates:
                flattened.append(
                    {
                        "word": alt,
                        "alternates": [],
                        "is_primary": False,
                        "primary_word": primary,
                    }
                )
        else:
            flattened.append({"word": item, "alternates": [], "is_primary": True})
    return flattened


def populate_words_from_json():
    """Populate words table from MW API JSON files"""
    mw_data_dir = Path("mw_data")

    if not mw_data_dir.exists():
        print("⚠️  mw_data directory not found. Run fetch_mw_data.py first!")
        return False

    # Check if already populated
    if len(list(words())) > 0:
        return True

    all_word_lists = [
        (1, flatten_word_list(ONE_BEE)),
        (2, flatten_word_list(TWO_BEE)),
        (3, flatten_word_list(THREE_BEE)),
    ]

    for level, word_list in all_word_lists:
        for word_info in word_list:
            word = word_info["word"]
            is_primary = word_info["is_primary"]

            # For primary words, load from JSON
            json_file = (
                mw_data_dir
                / f"{word if is_primary else word_info['primary_word']}.json"
            )

            if json_file.exists():
                with open(json_file) as f:
                    mw_data = json.load(f)

                # Build definition text
                definition_parts = []

                if mw_data.get("is_inflection") and mw_data.get("base_word"):
                    definition_parts.append(
                        f"({mw_data.get('functional_label', 'form')} of {mw_data['base_word']})"
                    )

                if mw_data.get("shortdef"):
                    definition_parts.extend(mw_data["shortdef"])

                definition = " • ".join(definition_parts) if definition_parts else ""

                words.insert(
                    word=word,
                    difficulty_level=level,
                    definition=definition,
                    functional_label=mw_data.get("functional_label", ""),
                    pronunciation=mw_data.get("pronunciation", ""),
                    has_audio=mw_data.get("has_audio", False),
                    audio_url=mw_data.get("audio_url", ""),
                    audio_file_local=f"audio/{['one_bee', 'two_bee', 'three_bee'][level - 1]}/{word}.mp3",
                    is_inflection=mw_data.get("is_inflection", False),
                    base_word=mw_data.get("base_word", ""),
                    is_primary=is_primary,
                    primary_word=word_info.get("primary_word", ""),
                )
            else:
                # No MW data, create minimal entry
                words.insert(
                    word=word,
                    difficulty_level=level,
                    definition="",
                    functional_label="",
                    pronunciation="",
                    has_audio=False,
                    audio_url="",
                    audio_file_local=f"audio/{['one_bee', 'two_bee', 'three_bee'][level - 1]}/{word}.mp3",
                    is_inflection=False,
                    base_word="",
                    is_primary=is_primary,
                    primary_word=word_info.get("primary_word", ""),
                )

    return True


# Populate words on startup
populate_words_from_json()

# SRS Configuration
SRS_INTERVALS = {
    0: timedelta(minutes=5),
    1: timedelta(hours=1),
    2: timedelta(hours=6),
    3: timedelta(days=1),
    4: timedelta(days=3),
    5: timedelta(weeks=1),
}


def jumble_word(word):
    """Jumble word ensuring result is different from original"""
    if len(word) <= 1:
        return word

    jumbled = None
    attempts = 0
    while (jumbled is None or jumbled == word) and attempts < 100:
        letters = list(word)
        random.shuffle(letters)
        jumbled = "".join(letters)
        attempts += 1

    if jumbled == word and len(word) > 1:
        letters = list(word)
        letters[0], letters[1] = letters[1], letters[0]
        jumbled = "".join(letters)

    return jumbled


def get_next_word(user_id, difficulty_level):
    """SRS-based word selection - only primary words"""
    now = datetime.now().isoformat()

    # Get all PRIMARY words at this difficulty
    all_words = words(where=f"difficulty_level = {difficulty_level} AND is_primary = 1")

    user_progress = {}
    for prog in user_word_progress(where=f"user_id = {user_id}"):
        user_progress[prog.word_id] = prog

    due_words = []
    new_words = []

    for word in all_words:
        if word.id not in user_progress:
            new_words.append(word)
        else:
            prog = user_progress[word.id]
            if prog.next_review_at <= now:
                priority = 10 - prog.mastery_level
                due_words.extend([word] * priority)

    if due_words and random.random() < 0.7:
        return random.choice(due_words)
    elif new_words:
        return random.choice(new_words)
    elif due_words:
        return random.choice(due_words)
    else:
        return random.choice(all_words)


def check_answer_against_alternates(answer, word_id):
    """Check if answer matches primary word or any alternates"""
    word = words[word_id]

    print(f"  Checking Answer: {answer} against word object:")
    print(f"    word.word = '{word.word}'")
    print(f"    word.is_primary = {word.is_primary}")
    print(f"    word.primary_word = '{word.primary_word}'")

    # Check primary word
    if answer == word.word.lower():
        print(f"  ✓ Match: answer == word.word")
        return True

    # If this is an alternate, check its primary
    if not word.is_primary and word.primary_word:
        print(f"  Checking primary word: '{word.primary_word}'")
        if answer == word.primary_word.lower():
            print(f"  ✓ Match: answer == primary_word")
            return True

    # Check all alternates of the primary word
    if word.is_primary:
        alternates = words(where=f"primary_word = '{word.word}'")
        print(f"  Checking {len(alternates)} alternates...")
        for alt in alternates:
            print(f"    Checking alternate: '{alt.word}'")
            if answer == alt.word.lower():
                print(f"  ✓ Match: answer == alternate '{alt.word}'")
                return True

    print(f"  ✗ No match found")
    return False


def update_progress(user_id, word_id, correct):
    """Update user progress with SRS logic"""
    now = datetime.now()

    try:
        prog = user_word_progress(where=f"user_id = {user_id} AND word_id = {word_id}")[
            0
        ]
        prog = UserProgress(**prog.__dict__)
    except IndexError:
        prog = UserProgress(
            id=None,
            user_id=user_id,
            word_id=word_id,
            times_attempted=0,
            times_correct=0,
            times_incorrect=0,
            first_attempted_at=now.isoformat(),
            last_attempted_at=now.isoformat(),
            next_review_at=now.isoformat(),
            current_streak=0,
            mastery_level=0,
        )

    prog.times_attempted += 1
    prog.last_attempted_at = now.isoformat()

    if correct:
        prog.times_correct += 1
        prog.current_streak += 1
        prog.mastery_level = min(5, prog.mastery_level + 1)
    else:
        prog.times_incorrect += 1
        prog.current_streak = 0
        prog.mastery_level = max(0, prog.mastery_level - 1)

    interval = SRS_INTERVALS.get(prog.mastery_level, timedelta(weeks=2))
    prog.next_review_at = (now + interval).isoformat()

    print(f"progress insert: {prog}")
    if prog.id is None:
        user_word_progress.insert(prog)
    else:
        user_word_progress.update(prog)


def get_user_stats(user_id, difficulty_level):
    """Get statistics for progress display - only for primary words"""
    all_words = words(where=f"difficulty_level = {difficulty_level} AND is_primary = 1")
    total = len(all_words)

    mastered = 0
    in_progress = 0

    for word in all_words:
        try:
            prog = user_word_progress(
                where=f"user_id = {user_id} AND word_id = {word.id}"
            )[0]
            if prog.mastery_level >= 5:
                mastered += 1
            elif prog.mastery_level > 0:
                in_progress += 1
        except IndexError:
            pass

    return {
        "total": total,
        "mastered": mastered,
        "in_progress": in_progress,
        "not_started": total - mastered - in_progress,
        "mastery_pct": int((mastered / total) * 100) if total > 0 else 0,
        "progress_pct": int(((mastered + in_progress) / total) * 100)
        if total > 0
        else 0,
    }


# FastHTML app
app, rt = fast_app(hdrs=Theme.blue.headers(mode="dark"), live=True)

session_state = {}


def get_session(user_id):
    """Get or create session state"""
    if user_id not in session_state:
        session_state[user_id] = {
            "current_word": None,
            "jumbled": None,
            "difficulty": 1,
            "show_hint": False,
            "current_answer": "",  # Preserve answer across hint toggles
        }
    return session_state[user_id]


# bee_gee = Style("""
#     .bg {
#     position: fixed;
#     inset: 0;
#     z-index: 0;
#     background-color: var(--bgee);
#     }
#     body {
#     --bgee: #f0f;
#
#     }
#     #correct-btn {
#     position: fixed;
#     top: 33px;
#     left: 333px;
#     right: 333px;
#     height: 50px;
#     display: flex;
#     justify-content: center;
#     align-items: center;
#     z-index: 1001;
#     }
#     #tornado {
#     height: 100vh;
#     width: 100vw;
#     overflow: hidden;
#     z-index: 1000;
#     position: fixed;
#     inset: 0;
#     }
# """)
# tornado = Script("""
# var animationRunning = true;
# function stopTornado(){
# animationRunning= false;
# }
# function startTornado(){
# animationRunning= true;
# frame()
# }
#
# function project3D(x, y, z, vars) {
#   var p, d;
#   x -= vars.camX;
#   y -= vars.camY - 8;
#   z -= vars.camZ;
#   p = Math.atan2(x, z);
#   d = Math.sqrt(x * x + z * z);
#   x = Math.sin(p - vars.yaw) * d;
#   z = Math.cos(p - vars.yaw) * d;
#   p = Math.atan2(y, z);
#   d = Math.sqrt(y * y + z * z);
#   y = Math.sin(p - vars.pitch) * d;
#   z = Math.cos(p - vars.pitch) * d;
#   var rx1 = -1000;
#   var ry1 = 1;
#   var rx2 = 1000;
#   var ry2 = 1;
#   var rx3 = 0;
#   var ry3 = 0;
#   var rx4 = x;
#   var ry4 = z;
#   var uc = (ry4 - ry3) * (rx2 - rx1) - (rx4 - rx3) * (ry2 - ry1);
#   var ua = ((rx4 - rx3) * (ry1 - ry3) - (ry4 - ry3) * (rx1 - rx3)) / uc;
#   var ub = ((rx2 - rx1) * (ry1 - ry3) - (ry2 - ry1) * (rx1 - rx3)) / uc;
#   if (!z) z = 0.000000001;
#   if (ua > 0 && ua < 1 && ub > 0 && ub < 1) {
#     return {
#       x: vars.cx + (rx1 + ua * (rx2 - rx1)) * vars.scale,
#       y: vars.cy + (y / z) * vars.scale,
#       d: x * x + y * y + z * z
#     };
#   } else {
#     return {
#       d: -1
#     };
#   }
# }
#
# function elevation(x, y, z) {
#   var dist = Math.sqrt(x * x + y * y + z * z);
#   if (dist && z / dist >= -1 && z / dist <= 1) return Math.acos(z / dist);
#   return 0.00000001;
# }
#
# function rgb(col) {
#   col += 0.000001;
#   var r = parseInt((0.5 + Math.sin(col) * 0.5) * 16);
#   var g = parseInt((0.5 + Math.cos(col) * 0.5) * 16);
#   var b = parseInt((0.5 - Math.sin(col) * 0.5) * 16);
#   return "#" + r.toString(16) + g.toString(16) + b.toString(16);
# }
#
# function interpolateColors(RGB1, RGB2, degree) {
#   var w2 = degree;
#   var w1 = 1 - w2;
#   return [
#     w1 * RGB1[0] + w2 * RGB2[0],
#     w1 * RGB1[1] + w2 * RGB2[1],
#     w1 * RGB1[2] + w2 * RGB2[2]
#   ];
# }
#
# function rgbArray(col) {
#   col += 0.000001;
#   var r = parseInt((0.5 + Math.sin(col) * 0.5) * 256);
#   var g = parseInt((0.5 + Math.cos(col) * 0.5) * 256);
#   var b = parseInt((0.5 - Math.sin(col) * 0.5) * 256);
#   return [r, g, b];
# }
#
# function colorString(arr) {
#   var r = parseInt(arr[0]);
#   var g = parseInt(arr[1]);
#   var b = parseInt(arr[2]);
#   return (
#     "#" +
#     ("0" + r.toString(16)).slice(-2) +
#     ("0" + g.toString(16)).slice(-2) +
#     ("0" + b.toString(16)).slice(-2)
#   );
# }
#
# function process(vars) {
#   if (vars.points.length < vars.initParticles)
#     for (var i = 0; i < 5; ++i) spawnParticle(vars);
#   var p, d, t;
#   p = Math.atan2(vars.camX, vars.camZ);
#   d = Math.sqrt(vars.camX * vars.camX + vars.camZ * vars.camZ);
#   d -= Math.sin(vars.frameNo / 80) / 25;
#   t = Math.cos(vars.frameNo / 300) / 165;
#   vars.camX = Math.sin(p + t) * d;
#   vars.camZ = Math.cos(p + t) * d;
#   vars.camY = -Math.sin(vars.frameNo / 220) * 15;
#   vars.yaw = Math.PI + p + t;
#   vars.pitch = elevation(vars.camX, vars.camZ, vars.camY) - Math.PI / 2;
#   var t;
#   for (var i = 0; i < vars.points.length; ++i) {
#     x = vars.points[i].x;
#     y = vars.points[i].y;
#     z = vars.points[i].z;
#     d = Math.sqrt(x * x + z * z) / 1.0075;
#     t = 0.1 / (1 + (d * d) / 5);
#     p = Math.atan2(x, z) + t;
#     vars.points[i].x = Math.sin(p) * d;
#     vars.points[i].z = Math.cos(p) * d;
#     vars.points[i].y +=
#       vars.points[i].vy * t * ((Math.sqrt(vars.distributionRadius) - d) * 2);
#     if (vars.points[i].y > vars.vortexHeight / 2 || d < 0.25) {
#       vars.points.splice(i, 1);
#       spawnParticle(vars);
#     }
#   }
# }
#
# function drawFloor(vars) {
#   var x, y, z, d, point, a;
#   for (var i = -25; i <= 25; i += 1) {
#     for (var j = -25; j <= 25; j += 1) {
#       x = i * 2;
#       z = j * 2;
#       y = vars.floor;
#       d = Math.sqrt(x * x + z * z);
#       point = project3D(x, y - (d * d) / 85, z, vars);
#       if (point.d != -1) {
#         size = 1 + 15000 / (1 + point.d);
#         a = 0.15 - Math.pow(d / 50, 4) * 0.15;
#         if (a > 0) {
#           vars.ctx.fillStyle = colorString(
#             interpolateColors(
#               rgbArray(d / 26 - vars.frameNo / 40),
#               [0, 128, 32],
#               0.5 + Math.sin(d / 6 - vars.frameNo / 8) / 2
#             )
#           );
#           vars.ctx.globalAlpha = a;
#           vars.ctx.fillRect(point.x - size / 2, point.y - size / 2, size, size);
#         }
#       }
#     }
#   }
#   vars.ctx.fillStyle = "#82f";
#   for (var i = -25; i <= 25; i += 1) {
#     for (var j = -25; j <= 25; j += 1) {
#       x = i * 2;
#       z = j * 2;
#       y = -vars.floor;
#       d = Math.sqrt(x * x + z * z);
#       point = project3D(x, y + (d * d) / 85, z, vars);
#       if (point.d != -1) {
#         size = 1 + 15000 / (1 + point.d);
#         a = 0.15 - Math.pow(d / 50, 4) * 0.15;
#         if (a > 0) {
#           vars.ctx.fillStyle = colorString(
#             interpolateColors(
#               rgbArray(-d / 26 - vars.frameNo / 40),
#               [32, 0, 128],
#               0.5 + Math.sin(-d / 6 - vars.frameNo / 8) / 2
#             )
#           );
#           vars.ctx.globalAlpha = a;
#           vars.ctx.fillRect(point.x - size / 2, point.y - size / 2, size, size);
#         }
#       }
#     }
#   }
# }
#
# function sortFunction(a, b) {
#   return b.dist - a.dist;
# }
#
# function draw(vars) {
#   vars.ctx.globalAlpha = 0.15;
#   vars.ctx.fillStyle = "#000";
#   vars.ctx.fillRect(0, 0, tornado.width, tornado.height);
#   drawFloor(vars);
#   var point, x, y, z, a;
#   for (var i = 0; i < vars.points.length; ++i) {
#     x = vars.points[i].x;
#     y = vars.points[i].y;
#     z = vars.points[i].z;
#     point = project3D(x, y, z, vars);
#     if (point.d != -1) {
#       vars.points[i].dist = point.d;
#       size = 1 + vars.points[i].radius / (1 + point.d);
#       d = Math.abs(vars.points[i].y);
#       a = 0.8 - Math.pow(d / (vars.vortexHeight / 2), 1000) * 0.8;
#       vars.ctx.globalAlpha = a >= 0 && a <= 1 ? a : 0;
#       vars.ctx.fillStyle = rgb(vars.points[i].color);
#       if (
#         point.x > -1 &&
#         point.x < vars.canvas.width &&
#         point.y > -1 &&
#         point.y < vars.canvas.height
#       )
#         vars.ctx.fillRect(point.x - size / 2, point.y - size / 2, size, size);
#     }
#   }
#   vars.points.sort(sortFunction);
# }
#
# function spawnParticle(vars) {
#   var p, ls;
#   pt = {};
#   p = Math.PI * 2 * Math.random();
#   ls = Math.sqrt(Math.random() * vars.distributionRadius);
#   pt.x = Math.sin(p) * ls;
#   pt.y = -vars.vortexHeight / 2;
#   pt.vy = vars.initV / 20 + Math.random() * vars.initV;
#   pt.z = Math.cos(p) * ls;
#   pt.radius = 200 + 800 * Math.random();
#   pt.color = pt.radius / 1000 + vars.frameNo / 250;
#   vars.points.push(pt);
# }
#
# function frame(vars) {
#   if (vars === undefined) {
#     var vars = {};
#     vars.canvas = document.querySelector(".tornado");
#     // vars.canvas = document.getElementById("tornado");
#     vars.ctx = vars.canvas.getContext("2d");
#     vars.canvas.width = document.body.clientWidth;
#     vars.canvas.height = document.body.clientHeight;
#     window.addEventListener(
#       "resize",
#       function () {
#         vars.canvas.width = document.body.clientWidth;
#         vars.canvas.height = document.body.clientHeight;
#         vars.cx = vars.canvas.width / 2;
#         vars.cy = vars.canvas.height / 2;
#       },
#       true
#     );
#     vars.frameNo = 0;
#     vars.camX = 0;
#     vars.camY = 0;
#     vars.camZ = -14;
#     vars.pitch = elevation(vars.camX, vars.camZ, vars.camY) - Math.PI / 2;
#     vars.yaw = 0;
#     vars.cx = vars.canvas.width / 2;
#     vars.cy = vars.canvas.height / 2;
#     vars.bounding = 10;
#     vars.scale = 500;
#     vars.floor = 26.5;
#     vars.points = [];
#     vars.initParticles = 2000;
#     vars.initV = 0.01;
#     vars.distributionRadius = 800;
#     vars.vortexHeight = 25;
#   }
# if (animationRunning) {
#     vars.frameNo++;
#     requestAnimationFrame(function () {
#       frame(vars);
#     });
#     process(vars);
#     draw(vars);
#   }
# }
# window.frame = frame
#
# """)


@rt
def index():
    return Container(
        # bee_gee,
        # Div(cls="bg", id="bg"),
        # Canvas(cls="tornado", id="tornado"),
        # Button(id="correct-btn", onclick="stopTornado()"),
        # tornado,
        Div(cls="flex justify-between items-center mb-8 px-4 bg-gray-700 relative")(
            H1("🐝 Spelling Bee Study", cls="text-3xl font-bold text-blue-400"),
            Form(
                hx_get="/set_user",
                hx_target="#game-area",
                hx_swap="outerHTML",
                cls="min-w-[200px]",
            )(
                Select(
                    Option("Guest", value="guest"),
                    Option("Sage", value="2"),
                    Option("Test", value="3"),
                    name="user_id",
                    id="user-select",
                    cls=" text-white rounded-lg px-4 py-2 border border-gray-700 min-w-full",
                    hx_get="/set_user",
                    hx_trigger="change",
                    hx_target="#game-area",
                    hx_swap="outerHTML",
                )
            ),
        ),
        Div(id="game-area")(game_interface("guest")),
        cls=ContainerT.lg,
    )


def game_interface(user_id):
    if user_id == "guest":
        user_id_int = None
    else:
        user_id_int = int(user_id)

    session = get_session(user_id)
    difficulty = session["difficulty"]

    if user_id_int:
        stats = {
            1: get_user_stats(user_id_int, 1),
            2: get_user_stats(user_id_int, 2),
            3: get_user_stats(user_id_int, 3),
        }
    else:
        stats = None

    if session["current_word"] is None:
        if user_id_int:
            word = get_next_word(user_id_int, difficulty)
        else:
            # Guest mode: random primary word
            all_words = words(
                where=f"difficulty_level = {difficulty} AND is_primary = 1"
            )
            word = random.choice(all_words)

        session["current_word"] = word
        session["jumbled"] = jumble_word(word.word)
        session["show_hint"] = False

    word = session["current_word"]
    jumbled = session["jumbled"]

    return Div(
        # Difficulty selector
        Div(cls="flex gap-4 justify-center mb-8")(
            *[
                Button(
                    f"{['One', 'Two', 'Three'][i]} Bee",
                    hx_post=f"/set_difficulty",
                    hx_vals=f'{{"user_id": "{user_id}", "level": "{i + 1}"}}',
                    hx_target="#game-area",
                    hx_swap="outerHTML",
                    cls=ButtonT.primary if difficulty == i + 1 else ButtonT.default,
                )
                for i in range(3)
            ]
        ),
        # Progress bars
        (
            Div(cls="grid grid-cols-3 gap-4 mb-8")(
                *[
                    Div(cls="space-y-2")(
                        P(
                            f"{['One', 'Two', 'Three'][i]} Bee",
                            cls=TextPresets.muted_sm,
                        ),
                        Progress(
                            value=str(stats[i + 1]["progress_pct"]),
                            max="100",
                            cls="w-full",
                        ),
                        P(
                            f"{stats[i + 1]['mastered']}/{stats[i + 1]['total']} mastered",
                            cls="text-xs text-gray-400",
                        ),
                    )
                    for i in range(3)
                ]
            )
            if stats
            else None
        ),
        game_card(user_id, word, jumbled, session["show_hint"], session),
        id="game-area",
    )


def game_card(user_id, word, jumbled, show_hint, session):
    # show_hint = True
    word_str = word.word
    word_length = len(word_str)

    # Always use local audio file (downloaded from MW or manually recorded)
    audio_src = word.audio_file_local
    # if os.path.exists(audio_src):
    #     print(f"adio src{audio_src}")
    show_hint = os.path.exists(audio_src)

    return Card(
        # Main prompt and hint side-by-side (only when hint is shown)
        Div(
            cls="grid gap-8 mb-8"
            + (" grid-cols-1 lg:grid-cols-2" if show_hint else " grid-cols-1")
        )(
            # Main prompt
            Div(cls="text-center space-y-4")(
                H3("Word Jumble", cls="text-xl text-blue-400"),
                P(
                    jumbled.upper(),
                    cls="text-4xl font-bold tracking-widest text-purple-400",
                ),
                (
                    Div(cls="mt-4 p-4 bg-gray-700 rounded-lg")(
                        P("Definition:", cls="text-sm text-gray-400 mb-2"),
                        P(word.definition, cls="text-base"),
                    )
                    if word.definition
                    else None
                ),
            ),
            # Hint (only visible when show_hint is True)
            (
                Div(cls="text-center space-y-4")(
                    H3("💡 Hint", cls="text-xl text-yellow-400"),
                    Div(cls="flex justify-center")(
                        Button(
                            UkIcon("volume-2", height=48, width=48),
                            cls="bg-blue-600 hover:bg-blue-700 text-white rounded-full p-6",
                            onclick=f"new Audio('{audio_src}').play()",
                        )
                    ),
                    (
                        P(f"/{word.pronunciation}/", cls="text-sm text-gray-400 mt-2")
                        if word.pronunciation
                        else None
                    ),
                )
                if show_hint
                else None
            ),
        ),
        # Single text input with letter spacing
        Form(
            Div(
                Input(type="hidden", value=user_id, name="user_id"),
                Input(type="hidden", value=word.id, name="word_id"),
                Input(type="hidden", value=word_str, name="word"),
                Input(
                    type="text",
                    name="answer",
                    id="answer-input",
                    value=session.get("current_answer", ""),  # Restore saved answer
                    maxlength=str(word_length),
                    placeholder="Type your answer...",
                    autocomplete="off",
                    autocapitalize="off",
                    spellcheck="false",
                    cls="text-center text-2xl font-bold tracking-[0.5em] rounded-lg border-2 bg-gray-700 text-white focus:outline-none focus:border-blue-500 px-8 py-4 uppercase",
                    autofocus=True,
                ),
                cls="flex justify-center mb-6",
            ),
            # Action buttons
            Div(
                Button(
                    UkIcon("lightbulb", cls="mr-2"),
                    "Hide Hint" if show_hint else "Show Hint",
                    type="button",
                    hx_post="/toggle_hint",
                    hx_vals=f'{{"user_id": "{user_id}"}}',
                    hx_target="#game-area",
                    hx_swap="outerHTML",
                    hx_include='[name="answer"]',
                    cls=ButtonT.secondary,
                ),
                Button("Submit", type="submit", cls=ButtonT.primary),
                Button(
                    UkIcon("rotate-ccw", cls="mr-2"),
                    "Clear",
                    type="button",
                    onclick='document.getElementById("answer-input").value = ""; document.getElementById("answer-input").focus();',
                    cls=ButtonT.default,
                ),
                cls="flex gap-4 justify-center",
            ),
            # action="/check_answer",
            # method="POST",
            hx_post="/check_answer",
            hx_vals=f'{{"user_id": "{user_id}", "word_id": {word.id}, "word": "{word_str}"}}',
            hx_target="#game-area",
            hx_swap="outerHTML",
            # hx_include="#answer-input",
            hx_include='[name="answer"]',
        ),
        cls="bg-gray-800",
    )


# @rt("/set_user")
# def get(user_id: str):kV
#     return game_interface(user_id)


@rt
def set_user(user_id: str):
    return game_interface(user_id)


@rt
def set_difficulty(level: int, user_id: str):
    session = get_session(user_id)
    session["difficulty"] = level
    session["current_word"] = None
    return game_interface(user_id)


@rt
def toggle_hint(user_id: str):
    session = get_session(user_id)
    session["show_hint"] = not session["show_hint"]
    return game_interface(user_id)


@rt
def check_answer(user_id: str, word_id: int, word: str, answer: str):
    print(f"word : {word}; answer: {answer}")
    # letters = []
    # i = 0
    # while f"letter_{i}" in kwargs:
    #     letters.append(kwargs[f"letter_{i}"].lower())
    #     i += 1

    # answer = "".join(letters)
    correct = check_answer_against_alternates(answer, word_id)

    if user_id != "guest":
        update_progress(int(user_id), word_id, correct)

    session = get_session(user_id)

    if correct:
        session["current_word"] = None
        return Div(
            Toast(
                DivLAligned(UkIcon("check-circle", cls="mr-2"), "🎉 Correct!"),
                cls=AlertT.success,
            ),
            game_interface(user_id),
            id="game-area",
        )
    else:
        return Div(
            Toast(
                DivLAligned(UkIcon("x-circle", cls="mr-2"), "❌ Try again!"),
                cls=AlertT.error,
            ),
            game_interface(user_id),
            id="game-area",
        )


serve()

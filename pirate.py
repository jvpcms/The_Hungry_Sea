import math, os, random, sys
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from direct.gui.DirectGui import DirectFrame, DirectButton, DGG
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    GeomTriangles, Geom, GeomNode,
    LVector3f, LColor,
    AmbientLight, DirectionalLight,
    LineSegs, WindowProperties, TextNode, Shader, Fog, LPoint2f,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_SPEED    = 32.0
TURN_SPEED   = 55.0
ACCELERATION = 28.0
DRAG         = 0.7
CAM_DIST      = 110.0
CAM_PITCH_MIN =   5.0
CAM_PITCH_MAX =  75.0
MOUSE_SENS_H  =  80.0
MOUSE_SENS_V  =  50.0

PITCH_AMPLITUDE = 2.5
PITCH_PERIOD    = 7.0
ROLL_AMPLITUDE  = 4.0
ROLL_PERIOD     = 5.0
HULL_DRAFT      = 4.0

CANNON_SPEED     = 50.0
CANNON_MAX_RANGE = 130.0
CANNON_MIN_RANGE = 15.0
CANNON_AIM_RATE  = 70.0    # units/second while holding aim button
CANNON_GRAVITY   = -28.0
CANNON_Z         = 3.0

WORLD_RANGE = 2000.0
MINI_RANGE  =  600.0   # world units visible in the minimap circle
MINI_HALF   = 0.16
FULL_HALF   = 0.75

if getattr(sys, 'frozen', False):
    _BASE = os.path.dirname(sys.executable)
else:
    _BASE = os.path.dirname(os.path.abspath(__file__))
ASSETS     = os.path.join(_BASE, 'assets')
SOUND_DIR  = os.path.join(ASSETS, 'sound')

def _model(name):
    bam = os.path.join(ASSETS, 'models', 'BAM', name + '.bam')
    obj = os.path.join(ASSETS, 'models', 'OBJ', name + '.obj')
    return bam if os.path.exists(bam) else obj

SHIP_MODEL       = _model('ship-large')
ENEMY_SHIP_MODEL = _model('ship-pirate-large')
BALL_MODEL       = _model('cannon-ball')

PLAYER_GOLD_START = 500
PLAYER_AMMO_START = 20
MAX_CARGO         = 100

# Item catalogue — cargo=False items track quantity but don't fill the hold
ITEMS = {
    'Rum':          {'cat': 'Goods',   'cargo': True},
    'Spices':       {'cat': 'Goods',   'cargo': True},
    'Silk':         {'cat': 'Goods',   'cargo': True},
    'Food':         {'cat': 'Goods',   'cargo': True},
    'Coconuts':     {'cat': 'Goods',   'cargo': True},
    'Fruit':        {'cat': 'Goods',   'cargo': True},
    'Hull Planks':  {'cat': 'Repairs', 'cargo': True,  'heal': 30},
    'Rope':         {'cat': 'Repairs', 'cargo': True,  'heal': 15},
    'Sails':        {'cat': 'Repairs', 'cargo': True,  'heal': 25},
    'Cannonballs':  {'cat': 'Ammo',    'cargo': True,  'dmg':  25},
    'Sea Mines':    {'cat': 'Ammo',    'cargo': True,  'dmg':  50},
}

# Base market price per item.  Ports sell at this price and buy from the
# player at 0.5× if they stock it, or 1.5× if they don't.
ITEM_PRICE = {
    'Rum':         30,
    'Spices':      60,
    'Silk':        80,
    'Food':        15,
    'Coconuts':    10,
    'Fruit':       12,
    'Hull Planks': 50,
    'Rope':        25,
    'Sails':       90,
    'Cannonballs': 20,
    'Sea Mines':   80,
}

PORTS = [
    {
        'name': 'Tortuga',
        'pos': LVector3f(0, 0, 0),
        'radius': 32.0,
        'trigger_r': 42.0,
        'sells': {'Rum', 'Spices', 'Silk', 'Food'},
    },
    {
        'name': 'Fort Ironcliff',
        'pos': LVector3f(-750, 620, 0),
        'radius': 35.0,
        'trigger_r': 48.0,
        'sells': {'Cannonballs', 'Sea Mines', 'Food'},
    },
    {
        'name': 'Palm Cove',
        'pos': LVector3f(280, -950, 0),
        'radius': 28.0,
        'trigger_r': 40.0,
        'sells': {'Coconuts', 'Fruit', 'Rum'},
    },
    {
        'name': "Shipwright's Cove",
        'pos': LVector3f(-500, -720, 0),
        'radius': 30.0,
        'trigger_r': 44.0,
        'sells': {'Hull Planks', 'Rope', 'Sails'},
    },
]

def _port_buy_price(item, port):
    """Price the port pays the player for one unit of item."""
    base = ITEM_PRICE[item]
    return max(1, int(base * (0.5 if item in port['sells'] else 1.5)))

# UI colours
_COL_TAB_ACTIVE    = (0.20, 0.50, 1.00, 1)
_COL_TAB_INACTIVE  = (0.08, 0.18, 0.38, 1)
_COL_FILT_ACTIVE   = (0.20, 0.55, 0.22, 1)
_COL_FILT_INACTIVE = (0.08, 0.20, 0.12, 1)

# Trade panel column X positions (shared by headers and data rows)
_TC_ITEM  = -0.72   # item name  (ALeft)
_TC_PRICE = -0.05   # price      (ACenter)
_TC_HAVE  =  0.32   # player qty (ACenter)
_TC_BTN   =  0.62   # button centre

# Inventory panel column X positions
_IC_ITEM = -0.55   # item name  (ALeft)
_IC_HAVE =  0.10   # quantity   (ACenter)
_IC_BTN  =  0.55   # Use/info button centre

# Mine / health HUD constants
MINE_RADIUS      = 6.0
MINE_DROP_OFFSET = 10.0   # drop this far behind the stern (> MINE_RADIUS)

ENEMY_HP          = 100
ENEMY_SPEED       = 35.0
ENEMY_TURN_SPEED  = 50.0
ENEMY_MIN_DIST    = 140.0
ENEMY_SHOOT_RANGE = 150.0
ENEMY_SHOOT_CD    = 5.0
ENEMY_SPAWN_DELAY = 30.0
ENEMY_SPAWN_DIST  = 450.0
ENEMY_PORT_SAFE_R = 150.0
ENEMY_DMG         = 25
ENEMY_HIT_R       = 35.0
SHIP_HIT_L        = 15.0   # half-length of ship OBB (forward/backward)
SHIP_HIT_W        =  6.5   # half-width  of ship OBB (left/right)
SINK_SPEED        = 2.5     # world units/second downward
SINK_TILT_SPEED   = 22.0    # degrees/second of death roll
SINK_DURATION     = 4.0     # seconds until removal / respawn
_HP_BAR_W    = 0.36
_HP_BAR_H    = 0.040
_HP_BAR_X    = -1.50
_HP_BAR_Z    = -0.95


# ---------------------------------------------------------------------------
# Shared GLSL water-pattern functions (ocean + sky both use these)
# ---------------------------------------------------------------------------

_WATER_LAYER_SRC = """
const float TWOPI = 6.283185307;
const float SIXPI = 18.84955592;

float circ(vec2 pos, vec2 c, float s) {
    c = abs(pos - c);
    c = min(c, 1.0 - c);
    return smoothstep(0.0, 0.002, sqrt(s) - sqrt(dot(c, c))) * -1.0;
}

float waterlayer(vec2 uv) {
    uv = mod(uv, 1.0);
    float ret = 1.0;
    ret += circ(uv, vec2(0.37378,  0.277169), 0.0268181);
    ret += circ(uv, vec2(0.031748, 0.540372), 0.0193742);
    ret += circ(uv, vec2(0.430044, 0.882218), 0.0232337);
    ret += circ(uv, vec2(0.641033, 0.695106), 0.0117864);
    ret += circ(uv, vec2(0.014640, 0.079135), 0.0299458);
    ret += circ(uv, vec2(0.43871,  0.394445), 0.0289087);
    ret += circ(uv, vec2(0.909446, 0.878141), 0.0284660);
    ret += circ(uv, vec2(0.310149, 0.686637), 0.0128496);
    ret += circ(uv, vec2(0.928617, 0.195986), 0.0152041);
    ret += circ(uv, vec2(0.043851, 0.868153), 0.0268601);
    ret += circ(uv, vec2(0.308619, 0.194937), 0.0080610);
    ret += circ(uv, vec2(0.349922, 0.449714), 0.0092867);
    ret += circ(uv, vec2(0.044956, 0.953415), 0.0231260);
    ret += circ(uv, vec2(0.117761, 0.503309), 0.0151272);
    ret += circ(uv, vec2(0.563517, 0.244991), 0.0292322);
    ret += circ(uv, vec2(0.566936, 0.954457), 0.0098114);
    ret += circ(uv, vec2(0.048994, 0.200931), 0.0178746);
    ret += circ(uv, vec2(0.569297, 0.624893), 0.0132408);
    ret += circ(uv, vec2(0.298347, 0.710972), 0.0114426);
    ret += circ(uv, vec2(0.878141, 0.771279), 0.0032272);
    ret += circ(uv, vec2(0.150995, 0.376221), 0.0021616);
    ret += circ(uv, vec2(0.119673, 0.541984), 0.0124621);
    ret += circ(uv, vec2(0.629598, 0.295629), 0.0198736);
    ret += circ(uv, vec2(0.334357, 0.266278), 0.0187145);
    ret += circ(uv, vec2(0.918044, 0.968163), 0.0182928);
    ret += circ(uv, vec2(0.965445, 0.505026), 0.0063480);
    ret += circ(uv, vec2(0.514847, 0.865444), 0.0062352);
    ret += circ(uv, vec2(0.710575, 0.041513), 0.0032269);
    ret += circ(uv, vec2(0.714030, 0.576945), 0.0215641);
    ret += circ(uv, vec2(0.748873, 0.413325), 0.0110795);
    ret += circ(uv, vec2(0.062337, 0.896713), 0.0236203);
    ret += circ(uv, vec2(0.980482, 0.473849), 0.0057344);
    ret += circ(uv, vec2(0.647463, 0.654349), 0.0188713);
    ret += circ(uv, vec2(0.651406, 0.981297), 0.0071088);
    ret += circ(uv, vec2(0.428928, 0.382426), 0.0298806);
    ret += circ(uv, vec2(0.811545, 0.625680), 0.0026554);
    ret += circ(uv, vec2(0.400787, 0.741620), 0.0048661);
    ret += circ(uv, vec2(0.331283, 0.418536), 0.0059803);
    ret += circ(uv, vec2(0.894762, 0.065800), 0.0076038);
    ret += circ(uv, vec2(0.525104, 0.572233), 0.0141796);
    ret += circ(uv, vec2(0.431526, 0.911372), 0.0213234);
    ret += circ(uv, vec2(0.658212, 0.910553), 0.0007410);
    ret += circ(uv, vec2(0.514523, 0.243263), 0.0270685);
    ret += circ(uv, vec2(0.024949, 0.252872), 0.0087665);
    ret += circ(uv, vec2(0.502214, 0.472690), 0.0234534);
    ret += circ(uv, vec2(0.693271, 0.431469), 0.0246533);
    ret += circ(uv, vec2(0.415000, 0.884418), 0.0271696);
    ret += circ(uv, vec2(0.149073, 0.412040), 0.0049720);
    ret += circ(uv, vec2(0.533816, 0.897634), 0.0065083);
    ret += circ(uv, vec2(0.040913, 0.834060), 0.0191398);
    ret += circ(uv, vec2(0.638585, 0.646019), 0.0206129);
    ret += circ(uv, vec2(0.660342, 0.966541), 0.0053511);
    ret += circ(uv, vec2(0.513783, 0.142233), 0.0047165);
    ret += circ(uv, vec2(0.124305, 0.644263), 0.0011672);
    ret += circ(uv, vec2(0.998710, 0.583864), 0.0107329);
    ret += circ(uv, vec2(0.894879, 0.233289), 0.0066709);
    ret += circ(uv, vec2(0.246286, 0.682766), 0.0041162);
    ret += circ(uv, vec2(0.076190, 0.163270), 0.0145935);
    ret += circ(uv, vec2(0.949386, 0.802936), 0.0100873);
    ret += circ(uv, vec2(0.480122, 0.196554), 0.0110185);
    ret += circ(uv, vec2(0.896854, 0.803707), 0.0139690);
    ret += circ(uv, vec2(0.292865, 0.762973), 0.0056641);
    ret += circ(uv, vec2(0.099559, 0.117457), 0.0086941);
    ret += circ(uv, vec2(0.377713, 0.003354), 0.0063147);
    ret += circ(uv, vec2(0.506365, 0.531118), 0.0144016);
    ret += circ(uv, vec2(0.408806, 0.894771), 0.0243923);
    ret += circ(uv, vec2(0.143579, 0.851380), 0.0041853);
    ret += circ(uv, vec2(0.090281, 0.181775), 0.0108896);
    ret += circ(uv, vec2(0.780695, 0.394644), 0.0047548);
    ret += circ(uv, vec2(0.298036, 0.625531), 0.0032529);
    ret += circ(uv, vec2(0.218423, 0.714537), 0.0015721);
    ret += circ(uv, vec2(0.658836, 0.159556), 0.0022590);
    ret += circ(uv, vec2(0.987324, 0.146545), 0.0288391);
    ret += circ(uv, vec2(0.222646, 0.251694), 0.0009228);
    ret += circ(uv, vec2(0.159826, 0.528063), 0.0060529);
    return max(ret, 0.0);
}
"""

# ---------------------------------------------------------------------------
# Ocean shader
# ---------------------------------------------------------------------------

_OCEAN_VERT = """
#version 140
uniform mat4 p3d_ModelViewProjectionMatrix;
in vec4 p3d_Vertex;
out vec2 vPos;
void main() {
    gl_Position = p3d_ModelViewProjectionMatrix * p3d_Vertex;
    vPos = p3d_Vertex.xy;
}
"""

_OCEAN_FRAG = """
#version 140
uniform float time;
uniform vec2 camPos;
in vec2 vPos;
out vec4 p3d_FragColor;

const vec3 WATER_COL  = vec3(0.04, 0.38, 0.88);
const vec3 WATER2_COL = vec3(0.04, 0.35, 0.78);
const vec3 FOAM_COL   = vec3(0.8125, 0.9609, 0.9648);
""" + _WATER_LAYER_SRC + """
vec3 water(vec2 uv, float iTime) {
    uv *= 0.25;
    float d1 = mod(uv.x + uv.y, TWOPI);
    float d2 = mod((uv.x + uv.y + 0.25) * 1.3, SIXPI);
    d1 = iTime * 0.07 + d1;
    d2 = iTime * 0.50 + d2;
    vec2 dist = vec2(sin(d1)*0.15 + sin(d2)*0.05,
                     cos(d1)*0.15 + cos(d2)*0.05);
    vec3 col = mix(WATER_COL, WATER2_COL, waterlayer(uv + dist.xy));
    col = mix(col, FOAM_COL, waterlayer(vec2(1.0) - uv - dist.yx));
    return col;
}

void main() {
    vec2 uv  = vPos * (100.0 / 1800.0);
    vec3 col = water(uv, time * 2.0);
    float d  = length(vPos - camPos);
    float fade = 1.0 - smoothstep(200.0, 1000.0, d);
    vec3 sky = vec3(0.40, 0.68, 0.92);
    p3d_FragColor = vec4(mix(sky, col, fade), 1.0);
}
"""

# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _make_ocean(size=2000):
    fmt   = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData('ocean', fmt, Geom.UHStatic)
    vdata.setNumRows(4)
    vw = GeomVertexWriter(vdata, 'vertex')
    cw = GeomVertexWriter(vdata, 'color')
    c  = (0.04, 0.20, 0.52, 1)
    for x, y in [(-size, -size), (size, -size), (size, size), (-size, size)]:
        vw.addData3(x, y, 0)
        cw.addData4(*c)
    tris = GeomTriangles(Geom.UHStatic)
    tris.addVertices(0, 1, 2)
    tris.addVertices(0, 2, 3)
    g  = Geom(vdata); g.addPrimitive(tris)
    gn = GeomNode('ocean'); gn.addGeom(g)
    return gn


def _make_ocean_grid(size=900, spacing=50):
    ls = LineSegs('ocean_grid')
    ls.setColor(0.10, 0.32, 0.70, 0.7)
    ls.setThickness(1.0)
    for i in range(-size, size + 1, spacing):
        ls.moveTo(i, -size, 0.15)
        ls.drawTo(i,  size, 0.15)
        ls.moveTo(-size, i, 0.15)
        ls.drawTo( size, i, 0.15)
    return ls.create()


def _make_placeholder_ship():
    fmt   = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData('ship', fmt, Geom.UHStatic)
    hw, hl, hh = 1.5, 5.0, 1.2
    verts = [
        (-hw, -hl, -hh), ( hw, -hl, -hh), ( hw,  hl, -hh), (-hw,  hl, -hh),
        (-hw, -hl,  hh), ( hw, -hl,  hh), ( hw,  hl,  hh), (-hw,  hl,  hh),
    ]
    faces = [
        (0,1,2,3), (7,6,5,4), (0,4,5,1),
        (2,6,7,3), (0,3,7,4), (1,5,6,2),
    ]
    colors = [
        (0.55, 0.35, 0.18, 1), (0.65, 0.42, 0.22, 1),
        (0.50, 0.30, 0.15, 1), (0.50, 0.30, 0.15, 1),
        (0.45, 0.28, 0.14, 1), (0.45, 0.28, 0.14, 1),
    ]
    all_v, all_c = [], []
    for face, col in zip(faces, colors):
        all_v.extend([verts[i] for i in face])
        all_c.extend([col] * 4)
    vdata.setNumRows(len(all_v))
    vw = GeomVertexWriter(vdata, 'vertex')
    cw = GeomVertexWriter(vdata, 'color')
    for v in all_v: vw.addData3(*v)
    for c in all_c: cw.addData4(*c)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(0, len(all_v), 4):
        tris.addVertices(i, i+1, i+2)
        tris.addVertices(i, i+2, i+3)
    g  = Geom(vdata); g.addPrimitive(tris)
    gn = GeomNode('ship'); gn.addGeom(g)
    return gn


def _make_hitbox_rect(half_l=SHIP_HIT_L, half_w=SHIP_HIT_W, color=(0.1, 0.9, 0.1, 1.0)):
    ls = LineSegs('hitbox_rect')
    ls.setColor(*color)
    ls.setThickness(2.5)
    corners = [
        (-half_w, -half_l, 0.3),
        ( half_w, -half_l, 0.3),
        ( half_w,  half_l, 0.3),
        (-half_w,  half_l, 0.3),
        (-half_w, -half_l, 0.3),
    ]
    ls.moveTo(*corners[0])
    for c in corners[1:]:
        ls.drawTo(*c)
    return ls.create()


def _make_landing_ring(r=3.5, n=20, color=(0.1, 0.9, 0.1, 1.0)):
    ls = LineSegs('landing_ring')
    ls.setColor(*color)
    ls.setThickness(2.5)
    pts = [(r * math.cos(2*math.pi*i/n), r * math.sin(2*math.pi*i/n), 0.3)
           for i in range(n + 1)]
    ls.moveTo(*pts[0])
    for p in pts[1:]:
        ls.drawTo(*p)
    return ls.create()


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

class PirateGame(ShowBase):
    def __init__(self):
        super().__init__()
        self.disableMouse()

        self.ship_pos     = LVector3f(0, -38, 0)
        self.ship_heading = -90.0   # facing east (+X)
        self.ship_speed   = 0.0
        self.cam_yaw      = 270.0   # camera west of ship = behind it
        self.cam_pitch    = 15.0
        self.paused       = False

        self.setBackgroundColor(0.40, 0.68, 0.92, 1)

        props = WindowProperties()
        props.setCursorHidden(True)
        props.setFullscreen(True)
        self.win.requestProperties(props)

        self._setup_audio()
        self._setup_lighting()
        self._setup_fog()
        self._setup_ocean()
        self._setup_ship()
        self._setup_islands()
        self._setup_keys()
        self._setup_aim()
        self._setup_maps()
        self._setup_economy()
        self._setup_hud()
        self._setup_enemy()
        self._setup_tooltip()
        self._setup_inventory()

        self._setup_pause_menu()

        self.taskMgr.add(self._update, 'update')
        self.accept('escape', self._toggle_pause)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_pause_menu(self):
        self.pause_panel = DirectFrame(
            parent=self.aspect2d,
            frameColor=(0.04, 0.10, 0.25, 0.97),
            frameSize=(-0.42, 0.42, -0.22, 0.22),
            pos=(0, 0, 0),
        )
        OnscreenText(
            parent=self.pause_panel, text='PAUSED',
            pos=(0, 0.12), scale=0.09,
            fg=(1.0, 0.88, 0.45, 1), align=TextNode.ACenter,
        )
        DirectButton(
            parent=self.pause_panel,
            text='Leave Game', text_scale=0.06,
            text_fg=(1, 1, 1, 1),
            frameSize=(-0.28, 0.28, -0.055, 0.075),
            frameColor=(0.55, 0.10, 0.10, 1),
            relief=1,
            pos=(0, 0, -0.06),
            command=self.userExit,
        )
        self.pause_panel.hide()

    def _toggle_pause(self):
        self.paused = not self.paused
        props = WindowProperties()
        if self.paused:
            self.pause_panel.show()
            props.setCursorHidden(False)
        else:
            self.pause_panel.hide()
            if not self.docked and not self.inv_open:
                props.setCursorHidden(True)
        self.win.requestProperties(props)

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------

    def _setup_audio(self):
        def _load(fname):
            p = os.path.join(SOUND_DIR, fname)
            if not os.path.exists(p):
                return None
            try:
                return self.loader.loadSfx(p)
            except Exception:
                return None

        self.snd_ocean = _load('wave_ambient.wav')
        if self.snd_ocean:
            self.snd_ocean.setLoop(True)
            self.snd_ocean.setVolume(0.45)
            self.snd_ocean.play()

        self.snd_battle = _load('battle_song.wav')
        if self.snd_battle:
            self.snd_battle.setLoop(True)
            self.snd_battle.setVolume(0.0)
            self.snd_battle.play()

        self.snd_seagulls = [s for s in [
            _load('Seagull Ambient 1.wav'), _load('Seagull Ambient 2.wav'),
            _load('Seagull Ambient 3.wav'), _load('Seagull Ambient 4.wav'),
            _load('Seagull Ambient 7.wav'),
        ] if s]
        self.snd_waves = [s for s in [
            _load('wave_short_1.flac'), _load('wave_short_2.flac'),
        ] if s]
        self.snd_wind = [s for s in [
            _load('Wind_short.ogg'), _load('Wind_short2.ogg'), _load('Wind_short3.ogg'),
        ] if s]

        self.amb_seagull_t = random.uniform(5,  15)
        self.amb_wave_t    = random.uniform(3,   8)
        self.amb_wind_t    = random.uniform(8,  20)

        self.snd_cannon_fire    = _load('cannon_fire.ogg')
        self.snd_cannon_hit     = _load('cannon_hit.ogg')
        self.snd_cannon_miss    = _load('cannon_miss.ogg')
        self.snd_mine_explode   = _load('mine_explode.wav')
        self.snd_ship_destroyed = _load('ship_destroyed.ogg')
        self.snd_gold           = _load('grabbing_gold.ogg') or _load('grabbing_gold.mp3')

    def _update_audio(self, dt):
        self.amb_seagull_t -= dt
        if self.amb_seagull_t <= 0 and self.snd_seagulls:
            random.choice(self.snd_seagulls).play()
            self.amb_seagull_t = random.uniform(8, 22)

        self.amb_wave_t -= dt
        if self.amb_wave_t <= 0 and self.snd_waves:
            random.choice(self.snd_waves).play()
            self.amb_wave_t = random.uniform(5, 12)

        self.amb_wind_t -= dt
        if self.amb_wind_t <= 0 and self.snd_wind:
            random.choice(self.snd_wind).play()
            self.amb_wind_t = random.uniform(10, 28)

        if self.snd_battle:
            if self.enemy and not self.enemy.get('dying'):
                dx = self.ship_pos.x - self.enemy['pos'].x
                dy = self.ship_pos.y - self.enemy['pos'].y
                dist = math.sqrt(dx*dx + dy*dy)
                target = max(0.0, min(0.85, (400.0 - dist) / (400.0 - 60.0)))
            else:
                target = 0.0
            cur = self.snd_battle.getVolume()
            self.snd_battle.setVolume(cur + (target - cur) * min(1.0, dt))

    def _setup_lighting(self):
        sun = DirectionalLight('sun')
        sun.setColor(LColor(1.0, 0.95, 0.85, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(45, -50, 0)
        self.render.setLight(sun_np)
        amb = AmbientLight('amb')
        amb.setColor(LColor(0.45, 0.48, 0.55, 1))
        self.render.setLight(self.render.attachNewNode(amb))

    def _setup_fog(self):
        fog = Fog('sea_fog')
        fog.setColor(0.40, 0.68, 0.92)   # match sky background colour
        fog.setLinearRange(200, 1000)     # starts at 200 units, fully opaque at 1000
        fog.setLinearFallback(45, 200, 1000)
        self.render.setFog(fog)
        self.ocean_np_fog = fog           # keep ref if needed later

    def _setup_ocean(self):
        self.ocean_np = self.render.attachNewNode(_make_ocean())
        self.ocean_np.setShader(Shader.make(Shader.SL_GLSL, _OCEAN_VERT, _OCEAN_FRAG))
        self.ocean_np.setShaderInput('time', 0.0)
        self.ocean_np.setShaderInput('camPos', 0.0, 0.0)
        self.ocean_np.setLightOff()   # flat cel shading — no lighting
        self.ocean_np.setFogOff()     # ocean has its own proximity fade in the shader

    def _setup_ship(self):
        self.ship_np = self.render.attachNewNode('ship_root')
        self.bob_np  = self.ship_np.attachNewNode('bob')

        if os.path.exists(SHIP_MODEL):
            model = self.loader.loadModel(SHIP_MODEL)
            model.reparentTo(self.bob_np)
            model.setHpr(90, 90, 90)
            model.setScale(3.0)
            model.setZ(-HULL_DRAFT)
        else:
            ph = self.bob_np.attachNewNode(_make_placeholder_ship())
            ph.setZ(-HULL_DRAFT)

        self.player_hitbox_np = self.ship_np.attachNewNode(
            _make_hitbox_rect(color=(0.2, 0.6, 1.0, 0.7)))
        self.player_hitbox_np.hide()

        self.ship_np.setPos(self.ship_pos)
        self.camLens.setFov(70)

    def _setup_islands(self):
        def place_all(port, pieces):
            np = self.render.attachNewNode(f'island_{port["name"]}')
            np.setPos(port['pos'])
            for fname, ox, oy, oz, h, scale in pieces:
                p = _model(fname.replace('.obj', ''))
                if not os.path.exists(p):
                    continue
                m = self.loader.loadModel(p)
                m.reparentTo(np)
                m.setPos(ox, oy, oz)
                m.setHpr(90 + h, 90, 90)
                m.setScale(scale)

        # ── Tortuga — trade hub, sandy shores, small watchtower ──────────
        place_all(PORTS[0], [
            ('rocks-sand-a.obj',               0,   0, -1,   0, 8),
            ('rocks-sand-b.obj',             -14,  10, -1,  60, 8),
            ('rocks-sand-c.obj',              14,   8, -1, -40, 7),
            ('palm-straight.obj',             -8, -10,  0,  20, 5),
            ('palm-bend.obj',                  7,  -8,  0, 200, 5),
            ('structure-platform-dock.obj',   -5, -20,  0,   0, 4),
            ('structure-platform-dock-small.obj', 9, -22, 0,  0, 4),
            ('tower-complete-small.obj',        0,  24,  0,   0, 4),
            ('barrel.obj',                    -9, -24,  1,  30, 3),
            ('barrel.obj',                    -3, -26,  1,  75, 3),
            ('crate.obj',                      7, -22,  1,   0, 3),
            ('cannon-mobile.obj',              1, -18,  1,   0, 4),
            ('flag-pirate-high.obj',           0, -14,  0,   0, 4),
        ])

        # ── Fort Ironcliff — fortress with grey rock, castle walls, towers ─
        place_all(PORTS[1], [
            # Grey rocky terrain
            ('rocks-a.obj',                   0,   0, -1,    0,  9),
            ('rocks-b.obj',                 -18,   8, -1,   45,  8),
            ('rocks-c.obj',                  16,  12, -1,  -30,  8),
            ('rocks-a.obj',                   8,  -8, -1,  130,  6),
            ('rocks-b.obj',                  -6,  18, -1,  -70,  6),
            # Castle walls forming a rough enclosure
            ('castle-wall.obj',             -10,   2,  0,    0,  5),
            ('castle-wall.obj',               4,   2,  0,    0,  5),
            ('castle-wall.obj',              -2,  10,  0,   90,  5),
            ('castle-gate.obj',              -2,  -8,  0,    0,  5),
            # Towers at flanks
            ('tower-complete-large.obj',    -22,  10,  0,    0,  5),
            ('tower-complete-large.obj',     18,   8,  0,    0,  5),
            ('tower-watch.obj',              -2,  20,  0,    0,  4),
            # Stone port platform
            ('structure-platform.obj',       -6, -20,  0,    0,  5),
            ('structure-platform.obj',        6, -20,  0,    0,  5),
            ('structure-platform-dock.obj',   0, -26,  0,    0,  4),
            # Cannons guarding the harbour
            ('cannon.obj',                  -12, -16,  1,    0,  4),
            ('cannon.obj',                   10, -16,  1,  180,  4),
            ('cannon-mobile.obj',             0, -12,  1,   90,  4),
            # Ammo props
            ('crate.obj',                    -5, -24,  1,   20,  3),
            ('barrel.obj',                    4, -26,  1,   60,  3),
            ('barrel.obj',                   -8, -26,  1,  -20,  3),
            # Flags
            ('flag-high.obj',               -22,  10,  0,    0,  4),
            ('flag-high.obj',                18,   8,  0,    0,  4),
            ('flag-pirate-high.obj',          0, -20,  0,    0,  4),
        ])

        # ── Palm Cove — lush tropical beach, sandy and green ─────────────
        place_all(PORTS[2], [
            # Sandy base
            ('patch-sand.obj',                0,   0, -0.5,   0, 12),
            ('patch-sand-foliage.obj',         8,  10, -0.5,  60,  8),
            ('patch-sand.obj',               -12,  -2, -0.5,  90,  7),
            # Lush detailed palms
            ('palm-detailed-straight.obj',   -6,  -4,   0,    0,  6),
            ('palm-detailed-straight.obj',   10,   6,   0,   80,  5),
            ('palm-detailed-bend.obj',       -14,   6,   0,  150,  5),
            ('palm-detailed-bend.obj',        12,  -6,   0,  280,  5),
            ('palm-straight.obj',             -2,  14,   0,  200,  4),
            ('palm-bend.obj',                  6,  12,   0,   40,  4),
            ('palm-bend.obj',                 -8,   8,   0,  330,  4),
            # Ground foliage
            ('grass-plant.obj',                2,   4,   0,    0,  3),
            ('grass-plant.obj',               -4,   2,   0,   90,  3),
            ('patch-grass-foliage.obj',         0,  -4,  0,   30,  5),
            # Small dock
            ('structure-platform-dock.obj',   -3, -18,   0,    0,  4),
            ('structure-platform-dock-small.obj', 8, -18, 0,   0,  3),
            # Tropical cargo props
            ('crate-bottles.obj',             -4, -20,   1,    0,  3),
            ('bottle-large.obj',               5, -18,   1,   45,  3),
            ('chest.obj',                     -8, -14,   0,    0,  3),
            ('flag-pirate-pennant.obj',         0, -12,   0,    0,  4),
        ])

        # ── Shipwright's Cove — boat repair yard, wooden docks, moored vessels
        place_all(PORTS[3], [
            # Rocky/sandy base
            ('rocks-sand-a.obj',               0,  12, -1,    0,  6),
            ('rocks-sand-b.obj',             -10,  18, -1,   60,  5),
            ('patch-sand.obj',                 4,  -2, -0.5,  30,  9),
            # Wooden dock platforms
            ('platform-planks.obj',           -8, -14,  0,    0,  6),
            ('platform-planks.obj',            6, -14,  0,    0,  6),
            ('platform.obj',                  -2,  -8,  0,   90,  5),
            # Dock structures
            ('structure-platform-dock.obj',   -6, -22,  0,    0,  4),
            ('structure-platform-dock.obj',    6, -22,  0,    0,  4),
            ('structure-platform-dock-small.obj', 14, -22, 0,  0,  3),
            # Moored rowboats
            ('boat-row-large.obj',            -8, -28,  0,   90,  6),
            ('boat-row-small.obj',             4, -28,  0,  270,  5),
            ('boat-row-small.obj',            14, -24,  0,  180,  4),
            # Mast and rigging props
            ('mast.obj',                      -4, -20,  0,    0,  5),
            ('mast-ropes.obj',                 6, -18,  0,    0,  4),
            # Dock fencing
            ('structure-fence.obj',          -14, -16,  0,    0,  4),
            ('structure-fence.obj',            8, -16,  0,    0,  4),
            ('structure-fence-sides.obj',     16, -22,  0,    0,  4),
            # Supply crates and barrels
            ('barrel.obj',                    -4, -22,  1,   30,  3),
            ('barrel.obj',                     2, -24,  1,   70,  3),
            ('crate.obj',                     10, -22,  1,    0,  3),
            ('crate.obj',                     -2, -26,  1,   45,  3),
            # Pennant flag
            ('flag-high-pennant.obj',           0, -16,  0,    0,  4),
        ])

    def _setup_keys(self):
        self.keys = {'w': False, 's': False, 'a': False, 'd': False}
        for key in self.keys:
            self.accept(key,        self._key_down, [key])
            self.accept(f'{key}-up', self._key_up,  [key])
        self.accept('i', self._toggle_inventory)

    def _key_down(self, key): self.keys[key] = True
    def _key_up(self,   key): self.keys[key] = False

    def _setup_aim(self):
        self.aim_dist       = (CANNON_MIN_RANGE + CANNON_MAX_RANGE) * 0.5
        self.mouse1_held    = False
        self.mouse3_held    = False
        self.aim_circle_on  = False
        self.aim_show_timer = 0.0
        self.projectiles    = []

        self.target_np = self.render.attachNewNode(
            _make_landing_ring(r=ENEMY_HIT_R))
        self.target_np.hide()

        self.enemy_target_np = self.render.attachNewNode(
            _make_landing_ring(r=ENEMY_HIT_R, color=(0.9, 0.1, 0.1, 1.0)))
        self.enemy_target_np.hide()

        self.accept('mouse1',    self._mouse1_down)
        self.accept('mouse1-up', self._mouse1_up)
        self.accept('mouse3',    self._mouse3_down)
        self.accept('mouse3-up', self._mouse3_up)
        self.accept('space',     self._fire)

    def _mouse1_down(self):
        self.mouse1_held   = True
        self.aim_circle_on = True
        self.aim_show_timer = 5.0

    def _mouse1_up(self):   self.mouse1_held = False

    def _mouse3_down(self):
        self.mouse3_held   = True
        self.aim_circle_on = True
        self.aim_show_timer = 5.0

    def _mouse3_up(self):   self.mouse3_held = False

    def _fire(self):
        if self.docked:
            return
        if self.inventory.get('Cannonballs', 0) <= 0:
            return
        self.aim_circle_on  = False
        self.aim_show_timer = 0.0
        if self.snd_cannon_fire: self.snd_cannon_fire.play()

        self.inventory['Cannonballs'] -= 1
        self._update_ammo_hud()

        land_d = self.aim_dist
        yr     = math.radians(self.cam_yaw)
        fdx, fdy = -math.sin(yr), -math.cos(yr)

        t_f = land_d / CANNON_SPEED
        vz  = (-CANNON_Z - 0.5 * CANNON_GRAVITY * t_f * t_f) / t_f

        ball_np = self.render.attachNewNode('cannonball')
        if os.path.exists(BALL_MODEL):
            m = self.loader.loadModel(BALL_MODEL)
            m.reparentTo(ball_np)
            m.setScale(5)
            m.setColor(0.15, 0.15, 0.15, 1)
        ball_np.setPos(self.ship_pos.x, self.ship_pos.y, CANNON_Z)
        lx = self.ship_pos.x + fdx * land_d
        ly = self.ship_pos.y + fdy * land_d
        ring_np = self.render.attachNewNode(_make_landing_ring(r=ENEMY_HIT_R))
        ring_np.setPos(lx, ly, 0)
        self.projectiles.append({
            'np':       ball_np,
            'ring_np':  ring_np,
            'pos':      LVector3f(self.ship_pos.x, self.ship_pos.y, CANNON_Z),
            'vel':      LVector3f(fdx * CANNON_SPEED, fdy * CANNON_SPEED, vz),
            'land_pos': LVector3f(lx, ly, 0),
        })

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def _update(self, task):
        dt = globalClock.getDt()
        self.ocean_np.setShaderInput('time', globalClock.getFrameTime())
        self.ocean_np.setShaderInput('camPos', self.camera.getX(), self.camera.getY())
        self._update_ship(dt)
        self._update_camera()
        self._update_aim(dt)
        self._update_projectiles(dt)
        self._update_mines(dt)
        self._update_enemy(dt)
        self._update_minimap()
        self._update_economy(dt)
        self._update_audio(dt)
        return Task.cont

    def _update_ship(self, dt):
        if self.player_dying:
            self._update_player_dying(dt)
            return
        if self.docked:
            return
        if self.keys['w']:
            self.ship_speed += ACCELERATION * dt
        if self.keys['s']:
            self.ship_speed -= ACCELERATION * dt

        self.ship_speed -= DRAG * self.ship_speed * dt
        self.ship_speed  = max(0.0, min(self.ship_speed, MAX_SPEED))

        turn_scale = 0.15 + 0.85 * (self.ship_speed / MAX_SPEED)
        if self.keys['a']:
            self.ship_heading += TURN_SPEED * turn_scale * dt
        if self.keys['d']:
            self.ship_heading -= TURN_SPEED * turn_scale * dt

        rad = math.radians(self.ship_heading)
        self.ship_pos.x -= math.sin(rad) * self.ship_speed * dt
        self.ship_pos.y += math.cos(rad) * self.ship_speed * dt

        # Collision against all island spheres
        for port in PORTS:
            dx   = self.ship_pos.x - port['pos'].x
            dy   = self.ship_pos.y - port['pos'].y
            dist = math.sqrt(dx*dx + dy*dy)
            if dist < port['radius']:
                if dist > 0:
                    self.ship_pos.x = port['pos'].x + (dx / dist) * port['radius']
                    self.ship_pos.y = port['pos'].y + (dy / dist) * port['radius']
                self.ship_speed = 0.0

        self.ship_np.setPos(self.ship_pos)
        self.ship_np.setH(self.ship_heading)

        t     = globalClock.getFrameTime()
        pitch = PITCH_AMPLITUDE * math.sin(t * (2 * math.pi / PITCH_PERIOD))
        roll  = ROLL_AMPLITUDE  * math.sin(t * (2 * math.pi / ROLL_PERIOD))
        self.bob_np.setHpr(0, pitch, roll)

    def _update_aim(self, dt):
        if not self.docked:
            if self.mouse1_held:
                self.aim_dist = min(self.aim_dist + CANNON_AIM_RATE * dt, CANNON_MAX_RANGE)
            if self.mouse3_held:
                self.aim_dist = max(self.aim_dist - CANNON_AIM_RATE * dt, CANNON_MIN_RANGE)

        yr  = math.radians(self.cam_yaw)
        fdx = -math.sin(yr)
        fdy = -math.cos(yr)

        if self.mouse1_held or self.mouse3_held:
            self.aim_show_timer = 5.0
        elif self.aim_circle_on:
            self.aim_show_timer -= dt
            if self.aim_show_timer <= 0:
                self.aim_circle_on = False

        if not self.docked and self.aim_circle_on:
            self.target_np.setPos(
                self.ship_pos.x + fdx * self.aim_dist,
                self.ship_pos.y + fdy * self.aim_dist,
                0,
            )
            self.target_np.show()
        else:
            self.target_np.hide()

    def _update_projectiles(self, dt):
        alive = []
        for p in self.projectiles:
            p['vel'].z += CANNON_GRAVITY * dt
            p['pos'].x += p['vel'].x * dt
            p['pos'].y += p['vel'].y * dt
            p['pos'].z += p['vel'].z * dt
            if p['pos'].z <= -1.0:
                hit = False
                if self.enemy and not self.enemy.get('dying'):
                    bx, by = p['pos'].x, p['pos'].y
                    dx = bx - self.enemy['pos'].x
                    dy = by - self.enemy['pos'].y
                    _hr = math.radians(self.enemy['heading'])
                    _lf = dx * (-math.sin(_hr)) + dy * math.cos(_hr)
                    _lr = dx *   math.cos(_hr)  + dy * math.sin(_hr)
                    nf = max(-SHIP_HIT_L, min(SHIP_HIT_L, _lf))
                    nr = max(-SHIP_HIT_W, min(SHIP_HIT_W, _lr))
                    hit = (_lf - nf)**2 + (_lr - nr)**2 < ENEMY_HIT_R * ENEMY_HIT_R
                if hit:
                    if self.snd_cannon_hit: self.snd_cannon_hit.play()
                    self._hit_enemy(ITEMS['Cannonballs']['dmg'])
                else:
                    if self.snd_cannon_miss: self.snd_cannon_miss.play()
                p['np'].removeNode()
                p['ring_np'].removeNode()
                continue
            p['np'].setPos(p['pos'])
            alive.append(p)
        self.projectiles = alive

    def _setup_maps(self):
        a2d = self.aspect2d
        ms  = MINI_HALF / WORLD_RANGE
        fs  = FULL_HALF / WORLD_RANGE

        ar  = self.getAspectRatio()
        self.mini_cx = ar - MINI_HALF - 0.03
        self.mini_cz = 1.0 - MINI_HALF - 0.03
        MCX, MCZ = self.mini_cx, self.mini_cz

        # ── Minimap (circular, player-centred) ───────────────────────────
        # Filled disc background
        N = 48
        fmt   = GeomVertexFormat.getV3c4()
        vdata = GeomVertexData('mini_disc', fmt, Geom.UHStatic)
        vdata.setNumRows(N + 2)
        vw = GeomVertexWriter(vdata, 'vertex')
        cw = GeomVertexWriter(vdata, 'color')
        bg = (0.03, 0.10, 0.25, 0.88)
        vw.addData3(MCX, 0, MCZ); cw.addData4(*bg)
        for i in range(N + 1):
            a = 2 * math.pi * i / N
            vw.addData3(MCX + MINI_HALF * math.cos(a), 0, MCZ + MINI_HALF * math.sin(a))
            cw.addData4(*bg)
        disc_tris = GeomTriangles(Geom.UHStatic)
        for i in range(N):
            disc_tris.addVertices(0, i + 1, i + 2)
        disc_g = Geom(vdata); disc_g.addPrimitive(disc_tris)
        disc_gn = GeomNode('mini_disc'); disc_gn.addGeom(disc_g)
        a2d.attachNewNode(disc_gn)

        # Circle border
        bls = LineSegs()
        bls.setColor(0.50, 0.62, 0.85, 1); bls.setThickness(2.0)
        for i in range(N + 1):
            a = 2 * math.pi * i / N
            x = MCX + MINI_HALF * math.cos(a)
            z = MCZ + MINI_HALF * math.sin(a)
            if i == 0: bls.moveTo(x, 0, z)
            else:       bls.drawTo(x, 0, z)
        a2d.attachNewNode(bls.create())

        # Port dots — repositioned every frame in _update_minimap
        self.mini_port_dots = []
        for _ in PORTS:
            dot = DirectFrame(parent=a2d, frameColor=(0.45, 0.88, 0.32, 1),
                              frameSize=(-0.009, 0.009, -0.009, 0.009),
                              pos=(MCX, 0, MCZ))
            self.mini_port_dots.append(dot)

        # Enemy dot — repositioned each frame, hidden when no enemy
        self.mini_enemy_dot = DirectFrame(
            parent=a2d, frameColor=(0.95, 0.15, 0.15, 1),
            frameSize=(-0.010, 0.010, -0.010, 0.010),
            pos=(MCX, 0, MCZ))
        self.mini_enemy_dot.hide()

        # Player arrow — always at centre
        als = LineSegs()
        als.setColor(1.0, 0.95, 0.1, 1); als.setThickness(2.0)
        s = 0.010
        als.moveTo(0, 0, s*2);  als.drawTo(-s, 0, -s)
        als.moveTo(-s, 0, -s);  als.drawTo(s,  0, -s)
        als.moveTo(s,  0, -s);  als.drawTo(0,  0, s*2)
        self.mini_player = a2d.attachNewNode(als.create())
        self.mini_player.setPos(MCX, 0, MCZ)

        # ── Full map ─────────────────────────────────────────────────────
        self.fullmap_np = a2d.attachNewNode('fullmap')
        self.fullmap_np.hide()

        DirectFrame(parent=self.fullmap_np,
                    frameColor=(0.00, 0.02, 0.08, 0.93),
                    frameSize=(-1.85, 1.85, -1.1, 1.1),
                    pos=(0, 0, 0))
        DirectFrame(parent=self.fullmap_np,
                    frameColor=(0.04, 0.12, 0.30, 1.0),
                    frameSize=(-FULL_HALF, FULL_HALF, -FULL_HALF, FULL_HALF),
                    pos=(0, 0, 0))

        fls = LineSegs()
        fls.setColor(0.50, 0.62, 0.85, 1); fls.setThickness(2.0)
        fh = FULL_HALF
        fls.moveTo(-fh, 0, -fh)
        for dx2, dz2 in [(fh,-fh),(fh,fh),(-fh,fh),(-fh,-fh)]:
            fls.drawTo(dx2, 0, dz2)
        self.fullmap_np.attachNewNode(fls.create())

        for port in PORTS:
            fix = port['pos'].x * fs
            fiz = port['pos'].y * fs
            DirectFrame(parent=self.fullmap_np, frameColor=(0.45, 0.88, 0.32, 1),
                        frameSize=(-0.018, 0.018, -0.018, 0.018),
                        pos=(fix, 0, fiz))
            OnscreenText(text=port['name'], pos=(fix, fiz + 0.055),
                         scale=0.060, fg=(0.65, 1.0, 0.45, 1),
                         shadow=(0,0,0,0.85), align=TextNode.ACenter,
                         parent=self.fullmap_np, mayChange=False)

        OnscreenText(text='WORLD MAP', pos=(0, 0.90),
                     scale=0.09, fg=(1,1,1,1), shadow=(0,0,0,0.8),
                     align=TextNode.ACenter,
                     parent=self.fullmap_np, mayChange=False)
        OnscreenText(text='[M] close', pos=(0, -0.92),
                     scale=0.055, fg=(0.6,0.6,0.6,1),
                     align=TextNode.ACenter,
                     parent=self.fullmap_np, mayChange=False)

        fals = LineSegs()
        fals.setColor(1.0, 0.95, 0.1, 1); fals.setThickness(3.0)
        fs2 = 0.022
        fals.moveTo(0, 0, fs2*2);   fals.drawTo(-fs2, 0, -fs2)
        fals.moveTo(-fs2, 0, -fs2); fals.drawTo(fs2,  0, -fs2)
        fals.moveTo(fs2,  0, -fs2); fals.drawTo(0,    0, fs2*2)
        self.full_player = self.fullmap_np.attachNewNode(fals.create())

        self.accept('m', self._toggle_fullmap)

    def _toggle_fullmap(self):
        if self.docked:
            return
        if self.fullmap_np.isHidden():
            self.fullmap_np.show()
        else:
            self.fullmap_np.hide()

    def _update_minimap(self):
        MCX, MCZ = self.mini_cx, self.mini_cz
        R   = MINI_HALF
        yr  = math.radians(self.cam_yaw)
        cyr = math.cos(yr)
        syr = math.sin(yr)

        # Player arrow at centre, rotated to match camera orientation
        self.mini_player.setPos(MCX, 0, MCZ)
        self.mini_player.setP(-(self.ship_heading + self.cam_yaw + 180))

        # Port dots — rotated so camera-forward = minimap-up
        for dot, port in zip(self.mini_port_dots, PORTS):
            dx = port['pos'].x - self.ship_pos.x
            dy = port['pos'].y - self.ship_pos.y
            dist = math.sqrt(dx*dx + dy*dy) or 0.001
            # Rotate offset into camera-relative screen space
            rx = -cyr * dx + syr * dy
            rz = -syr * dx - cyr * dy
            ratio = dist / MINI_RANGE
            if ratio <= 1.0:
                sx = MCX + rx / MINI_RANGE * R
                sz = MCZ + rz / MINI_RANGE * R
                dot['frameSize']  = (-0.009, 0.009, -0.009, 0.009)
                dot['frameColor'] = (0.45, 0.88, 0.32, 1)
            else:
                # Clamp direction to circle edge
                rdist = math.sqrt(rx*rx + rz*rz) or 0.001
                sx = MCX + (rx / rdist) * R * 0.93
                sz = MCZ + (rz / rdist) * R * 0.93
                dot['frameSize']  = (-0.006, 0.006, -0.006, 0.006)
                dot['frameColor'] = (0.45, 0.88, 0.32, 0.7)
            dot.setPos(sx, 0, sz)

        # Enemy dot
        if self.enemy:
            edx = self.enemy['pos'].x - self.ship_pos.x
            edy = self.enemy['pos'].y - self.ship_pos.y
            edist = math.sqrt(edx*edx + edy*edy) or 0.001
            erx = -cyr * edx + syr * edy
            erz = -syr * edx - cyr * edy
            if edist / MINI_RANGE <= 1.0:
                self.mini_enemy_dot.setPos(MCX + erx / MINI_RANGE * R, 0, MCZ + erz / MINI_RANGE * R)
                self.mini_enemy_dot['frameSize'] = (-0.010, 0.010, -0.010, 0.010)
            else:
                erdist = math.sqrt(erx*erx + erz*erz) or 0.001
                self.mini_enemy_dot.setPos(MCX + (erx / erdist) * R * 0.93, 0, MCZ + (erz / erdist) * R * 0.93)
                self.mini_enemy_dot['frameSize'] = (-0.007, 0.007, -0.007, 0.007)
            self.mini_enemy_dot.show()
        else:
            self.mini_enemy_dot.hide()

        if not self.fullmap_np.isHidden():
            fs = FULL_HALF / WORLD_RANGE
            fx = max(-FULL_HALF + 0.025, min(FULL_HALF - 0.025, self.ship_pos.x * fs))
            fz = max(-FULL_HALF + 0.025, min(FULL_HALF - 0.025, self.ship_pos.y * fs))
            self.full_player.setPos(fx, 0, fz)
            self.full_player.setP(-self.ship_heading)

    def _update_camera(self):
        if self.docked or self.inv_open or self.paused:
            return
        if self.mouseWatcherNode.hasMouse():
            dx = self.mouseWatcherNode.getMouseX()
            dy = self.mouseWatcherNode.getMouseY()
            # Radial deadzone — filters sub-pixel residual from movePointer lag
            dist = math.sqrt(dx*dx + dy*dy)
            if dist > 0.002:
                fac = (dist - 0.002) / dist   # smooth, no hard edge
                self.cam_yaw   += dx * fac * MOUSE_SENS_H
                self.cam_pitch -= dy * fac * MOUSE_SENS_V
                self.cam_pitch  = max(CAM_PITCH_MIN, min(CAM_PITCH_MAX, self.cam_pitch))
            w = self.win.getProperties().getXSize()
            h = self.win.getProperties().getYSize()
            self.win.movePointer(0, w // 2, h // 2)

        yr = math.radians(self.cam_yaw)
        pr = math.radians(self.cam_pitch)
        cx = self.ship_pos.x + math.sin(yr) * math.cos(pr) * CAM_DIST
        cy = self.ship_pos.y + math.cos(yr) * math.cos(pr) * CAM_DIST
        cz = max(1.0, self.ship_pos.z + math.sin(pr) * CAM_DIST)
        self.camera.setPos(cx, cy, cz)
        self.camera.lookAt(self.ship_pos.x, self.ship_pos.y, self.ship_pos.z + 3)

    # ------------------------------------------------------------------
    # Economy
    # ------------------------------------------------------------------
    # HUD & mines
    # ------------------------------------------------------------------

    def _setup_hud(self):
        self.health           = 100
        self.player_dying     = False
        self.player_die_timer = 0.0
        self.mines  = []

        # HP label to the left of the bar
        OnscreenText(text='HP', pos=(_HP_BAR_X - 0.06, _HP_BAR_Z + 0.010),
                     scale=0.046, fg=(1.0, 0.45, 0.45, 1), shadow=(0, 0, 0, 0.8),
                     align=TextNode.ARight, mayChange=False)
        # Background trough
        DirectFrame(parent=self.aspect2d,
                    frameColor=(0.12, 0.04, 0.04, 0.88),
                    frameSize=(0, _HP_BAR_W, 0, _HP_BAR_H),
                    pos=(_HP_BAR_X, 0, _HP_BAR_Z))
        # Coloured fill — width updated on damage
        self.hp_bar = DirectFrame(
                    parent=self.aspect2d,
                    frameColor=(0.15, 0.80, 0.20, 0.92),
                    frameSize=(0, _HP_BAR_W, 0, _HP_BAR_H),
                    pos=(_HP_BAR_X, 0, _HP_BAR_Z))
        self.hp_label = OnscreenText(
                    text='100',
                    pos=(_HP_BAR_X + _HP_BAR_W * 0.5, _HP_BAR_Z + 0.004),
                    scale=0.038, fg=(1, 1, 1, 1), shadow=(0, 0, 0, 0.75),
                    align=TextNode.ACenter, mayChange=True)

        self.accept('f', self._drop_mine)

    def _drop_mine(self):
        if self.docked:
            return
        if self.inventory.get('Sea Mines', 0) <= 0:
            return
        self.inventory['Sea Mines'] -= 1
        self._update_ammo_hud()

        # Place behind the stern: bow = (-sinH, cosH), so stern = (+sinH, -cosH)
        rad = math.radians(self.ship_heading)
        mx  = self.ship_pos.x + math.sin(rad) * MINE_DROP_OFFSET
        my  = self.ship_pos.y - math.cos(rad) * MINE_DROP_OFFSET

        mine_np  = self.render.attachNewNode('mine_root')
        mine_bob = mine_np.attachNewNode('mine_bob')
        p = _model('barrel')
        if os.path.exists(p):
            m = self.loader.loadModel(p)
            m.reparentTo(mine_bob)
            m.setHpr(90, 0, 0)   # barrel on its side — axis along world X
            m.setScale(2.8)
            m.setColor(0.06, 0.06, 0.10, 1)
        mine_np.setPos(mx, my, 0.4)
        phase = (mx * 0.13 + my * 0.07) % (2 * math.pi)
        self.mines.append({
            'np':    mine_np,
            'bob':   mine_bob,
            'pos':   LVector3f(mx, my, 0),
            'phase': phase,
        })

    def _update_mines(self, dt):
        t     = globalClock.getFrameTime()
        alive = []
        for mine in self.mines:
            # Buoyancy — same axes as ship but gentler amplitude
            ph    = mine['phase']
            pitch = PITCH_AMPLITUDE * 0.55 * math.sin((t + ph) * (2*math.pi / PITCH_PERIOD))
            roll  = ROLL_AMPLITUDE  * 0.55 * math.sin((t + ph * 1.37) * (2*math.pi / ROLL_PERIOD))
            mine['bob'].setHpr(0, pitch, roll)
            # Player collision
            dx = self.ship_pos.x - mine['pos'].x
            dy = self.ship_pos.y - mine['pos'].y
            if math.sqrt(dx*dx + dy*dy) < MINE_RADIUS:
                if self.snd_mine_explode: self.snd_mine_explode.play()
                mine['np'].removeNode()
                self._take_damage(50)
                continue
            # Enemy collision
            if self.enemy:
                edx = self.enemy['pos'].x - mine['pos'].x
                edy = self.enemy['pos'].y - mine['pos'].y
                if math.sqrt(edx*edx + edy*edy) < MINE_RADIUS:
                    if self.snd_mine_explode: self.snd_mine_explode.play()
                    mine['np'].removeNode()
                    self._hit_enemy(ITEMS['Sea Mines']['dmg'])
                    continue
            alive.append(mine)
        self.mines = alive

    # ------------------------------------------------------------------
    # Enemy
    # ------------------------------------------------------------------

    def _setup_enemy(self):
        self.enemy             = None
        self.enemy_spawn_timer = ENEMY_SPAWN_DELAY
        self.enemy_projectiles = []

        _bw, _bh = 0.11, 0.014
        self._ehp_bw = _bw
        self._ehp_bh = _bh
        self.enemy_hpbar_bg = DirectFrame(
            parent=self.aspect2d,
            frameSize=(-_bw, _bw, -_bh, _bh),
            frameColor=(0.25, 0.02, 0.02, 0.93))
        self.enemy_hpbar_fill = DirectFrame(
            parent=self.aspect2d,
            frameSize=(-_bw, _bw, -_bh, _bh),
            frameColor=(0.1, 0.9, 0.1, 0.93))
        self.enemy_hpbar_bg.hide()
        self.enemy_hpbar_fill.hide()

    def _near_any_port(self):
        for port in PORTS:
            dx = self.ship_pos.x - port['pos'].x
            dy = self.ship_pos.y - port['pos'].y
            if math.sqrt(dx*dx + dy*dy) < ENEMY_PORT_SAFE_R:
                return True
        return False

    def _spawn_enemy(self):
        angle = random.uniform(0, 2 * math.pi)
        ex = self.ship_pos.x + math.cos(angle) * ENEMY_SPAWN_DIST
        ey = self.ship_pos.y + math.sin(angle) * ENEMY_SPAWN_DIST

        root_np = self.render.attachNewNode('enemy_root')
        bob_np  = root_np.attachNewNode('enemy_bob')

        model_path = ENEMY_SHIP_MODEL if os.path.exists(ENEMY_SHIP_MODEL) else SHIP_MODEL
        if os.path.exists(model_path):
            m = self.loader.loadModel(model_path)
            m.reparentTo(bob_np)
            m.setHpr(90, 90, 90)
            m.setScale(3.0)
            m.setZ(-HULL_DRAFT)
        else:
            ph = self.render.attachNewNode(_make_placeholder_ship())
            ph.reparentTo(bob_np)
            ph.setColor(0.55, 0.08, 0.08, 1)

        hitbox_np = root_np.attachNewNode(
            _make_hitbox_rect(color=(1.0, 0.75, 0.0, 0.7)))
        hitbox_np.setPos(0, 0, 0)
        hitbox_np.hide()

        root_np.setPos(ex, ey, 0)

        self.enemy = {
            'np':        root_np,
            'bob':       bob_np,
            'hitbox_np': hitbox_np,
            'pos':       LVector3f(ex, ey, 0),
            'heading':   random.uniform(0, 360),
            'speed':     0.0,
            'hp':        ENEMY_HP,
            'shoot_cd':  ENEMY_SHOOT_CD,
        }

    def _update_enemy(self, dt):
        if self.enemy is None:
            self.enemy_spawn_timer -= dt
            if self.enemy_spawn_timer <= 0 and not self._near_any_port():
                self._spawn_enemy()
            return

        e = self.enemy
        if e.get('dying'):
            self._update_dying_enemy(dt)
            return

        dx = self.ship_pos.x - e['pos'].x
        dy = self.ship_pos.y - e['pos'].y
        dist = math.sqrt(dx*dx + dy*dy) or 0.001

        target_h = math.degrees(math.atan2(-dx, dy))
        diff = (target_h - e['heading'] + 180) % 360 - 180

        if dist > ENEMY_MIN_DIST:
            e['heading'] += max(-ENEMY_TURN_SPEED * dt, min(ENEMY_TURN_SPEED * dt, diff))
            e['speed'] = min(e['speed'] + 30.0 * dt, ENEMY_SPEED)
        else:
            perp_diff = 90.0
            e['heading'] += max(-ENEMY_TURN_SPEED * dt, min(ENEMY_TURN_SPEED * dt, perp_diff))
            e['speed'] = min(e['speed'] + 10.0 * dt, ENEMY_SPEED * 0.6)

        e['speed'] -= 0.7 * e['speed'] * dt

        rad = math.radians(e['heading'])
        e['pos'].x -= math.sin(rad) * e['speed'] * dt
        e['pos'].y += math.cos(rad) * e['speed'] * dt
        e['np'].setPos(e['pos'])
        e['np'].setH(e['heading'])

        t = globalClock.getFrameTime()
        pitch = PITCH_AMPLITUDE * math.sin(t * (2 * math.pi / PITCH_PERIOD) + 1.3)
        roll  = ROLL_AMPLITUDE  * math.sin(t * (2 * math.pi / ROLL_PERIOD)  + 0.7)
        e['bob'].setHpr(0, pitch, roll)

        e['shoot_cd'] -= dt
        if e['shoot_cd'] <= 0 and dist < ENEMY_SHOOT_RANGE:
            self._enemy_fire()
            e['shoot_cd'] = ENEMY_SHOOT_CD

        # Enemy aim ring — tracks the last in-flight enemy shot
        if self.enemy_projectiles:
            self.enemy_target_np.setPos(self.enemy_projectiles[-1]['land_pos'])
            self.enemy_target_np.show()
        else:
            self.enemy_target_np.hide()

        self._update_enemy_projectiles(dt)
        self._update_enemy_hpbar()

    def _update_enemy_hpbar(self):
        if not self.enemy or self.enemy.get('dying'):
            self.enemy_hpbar_bg.hide()
            self.enemy_hpbar_fill.hide()
            return
        e = self.enemy
        # Project world position above enemy to screen
        label_pos = LVector3f(e['pos'].x, e['pos'].y, 22)
        cam_rel   = self.camera.getRelativePoint(self.render, label_pos)
        p2        = LPoint2f()
        if not self.camLens.project(cam_rel, p2):
            self.enemy_hpbar_bg.hide()
            self.enemy_hpbar_fill.hide()
            return
        ar = self.getAspectRatio()
        sx = p2[0] * ar
        sz = p2[1]
        # Scale bar by inverse camera distance so it matches perceived ship size
        cam_pos     = self.camera.getPos(self.render)
        dist_to_cam = (cam_pos - LVector3f(e['pos'].x, e['pos'].y, 10)).length()
        bar_scale   = max(0.25, min(1.4, 55.0 / max(dist_to_cam, 1.0)))
        bw = self._ehp_bw * bar_scale
        bh = self._ehp_bh * bar_scale
        pct = max(0.0, e['hp'] / ENEMY_HP)
        r   = min(1.0, 2.0 * (1.0 - pct))
        g   = min(1.0, 2.0 * pct)
        self.enemy_hpbar_bg.setPos(sx, 0, sz)
        self.enemy_hpbar_bg['frameSize'] = (-bw, bw, -bh, bh)
        self.enemy_hpbar_bg.show()
        fill_hw = bw * pct
        self.enemy_hpbar_fill.setPos(sx - bw + fill_hw, 0, sz)
        self.enemy_hpbar_fill['frameSize']  = (-fill_hw, fill_hw, -bh, bh)
        self.enemy_hpbar_fill['frameColor'] = (r, g, 0.05, 0.93)
        if pct > 0:
            self.enemy_hpbar_fill.show()
        else:
            self.enemy_hpbar_fill.hide()

    def _enemy_fire(self):
        e  = self.enemy
        px, py = self.ship_pos.x, self.ship_pos.y
        ex, ey = e['pos'].x, e['pos'].y

        # Player velocity vector
        pr  = math.radians(self.ship_heading)
        pvx = -math.sin(pr) * self.ship_speed
        pvy =  math.cos(pr) * self.ship_speed

        dx0 = px - ex
        dy0 = py - ey

        # Solve |(dx0+pvx*t, dy0+pvy*t)| = CANNON_SPEED*t  →  quadratic in t
        a = pvx*pvx + pvy*pvy - CANNON_SPEED*CANNON_SPEED
        b = 2.0 * (dx0*pvx + dy0*pvy)
        c = dx0*dx0 + dy0*dy0
        disc = b*b - 4.0*a*c

        t_intercept = None
        if disc >= 0:
            sq = math.sqrt(disc)
            for ti in ((-b + sq) / (2*a), (-b - sq) / (2*a)):
                if ti > 0 and (t_intercept is None or ti < t_intercept):
                    t_intercept = ti

        if t_intercept is not None:
            aim_x = px + pvx * t_intercept
            aim_y = py + pvy * t_intercept
            aim_dist = math.sqrt((aim_x - ex)**2 + (aim_y - ey)**2)
            if aim_dist > CANNON_MAX_RANGE * 0.9:
                aim_x, aim_y = px, py
                aim_dist = math.sqrt(dx0*dx0 + dy0*dy0)
        else:
            aim_x, aim_y = px, py
            aim_dist = math.sqrt(dx0*dx0 + dy0*dy0)

        land_d = min(aim_dist, CANNON_MAX_RANGE * 0.9)
        fdx = (aim_x - ex) / max(aim_dist, 0.001)
        fdy = (aim_y - ey) / max(aim_dist, 0.001)

        spread = math.radians(random.uniform(-5, 5))
        cs, ss = math.cos(spread), math.sin(spread)
        fdx, fdy = fdx*cs - fdy*ss, fdx*ss + fdy*cs

        t_f = land_d / CANNON_SPEED
        vz  = (-CANNON_Z - 0.5 * CANNON_GRAVITY * t_f * t_f) / t_f

        if self.snd_cannon_fire: self.snd_cannon_fire.play()
        ball_np = self.render.attachNewNode('enemy_ball')
        if os.path.exists(BALL_MODEL):
            bm = self.loader.loadModel(BALL_MODEL)
            bm.reparentTo(ball_np)
            bm.setScale(5)
            bm.setColor(0.7, 0.1, 0.1, 1)
        ball_np.setPos(ex, ey, CANNON_Z)

        self.enemy_projectiles.append({
            'np':       ball_np,
            'pos':      LVector3f(ex, ey, CANNON_Z),
            'vel':      LVector3f(fdx * CANNON_SPEED, fdy * CANNON_SPEED, vz),
            'land_pos': LVector3f(ex + fdx * land_d, ey + fdy * land_d, 0),
        })

    def _update_enemy_projectiles(self, dt):
        alive = []
        for p in self.enemy_projectiles:
            p['vel'].z += CANNON_GRAVITY * dt
            p['pos'].x += p['vel'].x * dt
            p['pos'].y += p['vel'].y * dt
            p['pos'].z += p['vel'].z * dt
            p['np'].setPos(p['pos'])
            if p['pos'].z <= -1.0:
                dx = p['pos'].x - self.ship_pos.x
                dy = p['pos'].y - self.ship_pos.y
                _hr = math.radians(self.ship_heading)
                _lf = dx * (-math.sin(_hr)) + dy * math.cos(_hr)
                _lr = dx *   math.cos(_hr)  + dy * math.sin(_hr)
                nf = max(-SHIP_HIT_L, min(SHIP_HIT_L, _lf))
                nr = max(-SHIP_HIT_W, min(SHIP_HIT_W, _lr))
                if (_lf - nf)**2 + (_lr - nr)**2 < ENEMY_HIT_R * ENEMY_HIT_R:
                    if self.snd_cannon_hit: self.snd_cannon_hit.play()
                    self._take_damage(ENEMY_DMG)
                else:
                    if self.snd_cannon_miss: self.snd_cannon_miss.play()
                p['np'].removeNode()
            else:
                alive.append(p)
        self.enemy_projectiles = alive

    def _hit_enemy(self, dmg):
        if self.enemy is None:
            return
        self.enemy['hp'] = max(0, self.enemy['hp'] - dmg)
        if self.enemy['hp'] <= 0:
            self._kill_enemy()

    def _kill_enemy(self):
        if self.snd_ship_destroyed: self.snd_ship_destroyed.play()
        for p in self.enemy_projectiles:
            p['np'].removeNode()
        self.enemy_projectiles = []
        self.enemy_hpbar_bg.hide()
        self.enemy_hpbar_fill.hide()

        self.enemy['dying']    = True
        self.enemy['die_timer'] = 0.0

    def _update_dying_enemy(self, dt):
        e = self.enemy
        e['die_timer'] += dt
        t = e['die_timer']

        t_game    = globalClock.getFrameTime()
        pitch_bob = PITCH_AMPLITUDE * math.sin(t_game * (2 * math.pi / PITCH_PERIOD) + 1.3)
        roll_bob  = ROLL_AMPLITUDE  * math.sin(t_game * (2 * math.pi / ROLL_PERIOD)  + 0.7)
        tilt      = min(t * SINK_TILT_SPEED, 85.0)
        e['bob'].setHpr(0, pitch_bob, roll_bob + tilt)

        sink = t * SINK_SPEED
        e['np'].setPos(e['pos'].x, e['pos'].y, -sink)

        if t >= SINK_DURATION:
            e['np'].removeNode()
            self.enemy = None
            self.enemy_target_np.hide()
            self.enemy_spawn_timer = ENEMY_SPAWN_DELAY

    def _take_damage(self, amount):
        if self.player_dying:
            return
        self.health = max(0, self.health - amount)
        self._update_health_bar()
        if self.health <= 0:
            self._die()

    def _die(self):
        if self.snd_ship_destroyed: self.snd_ship_destroyed.play()
        if self.docked:
            self._undock()
        self.player_dying     = True
        self.player_die_timer = 0.0
        msg = OnscreenText(
            text='Ship sunk!  Respawning at Tortuga...',
            pos=(0, 0.15), scale=0.075,
            fg=(1.0, 0.30, 0.30, 1), shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter, mayChange=False,
        )
        self.taskMgr.doMethodLater(SINK_DURATION + 0.5, lambda t: msg.destroy(), 'death_msg')

    def _update_player_dying(self, dt):
        self.player_die_timer += dt
        t = self.player_die_timer

        t_game    = globalClock.getFrameTime()
        pitch_bob = PITCH_AMPLITUDE * math.sin(t_game * (2 * math.pi / PITCH_PERIOD))
        roll_bob  = ROLL_AMPLITUDE  * math.sin(t_game * (2 * math.pi / ROLL_PERIOD))
        tilt      = min(t * SINK_TILT_SPEED, 85.0)
        self.bob_np.setHpr(0, pitch_bob, roll_bob + tilt)

        sink = t * SINK_SPEED
        self.ship_np.setPos(self.ship_pos.x, self.ship_pos.y, -sink)

        if t >= SINK_DURATION:
            self._respawn_player()

    def _respawn_player(self):
        self.player_dying     = False
        self.player_die_timer = 0.0

        # Despawn any active or dying enemy
        if self.enemy is not None:
            for p in self.enemy_projectiles:
                p['np'].removeNode()
            self.enemy_projectiles = []
            self.enemy['np'].removeNode()
            self.enemy = None
            self.enemy_target_np.hide()
            self.enemy_hpbar_bg.hide()
            self.enemy_hpbar_fill.hide()
            self.enemy_spawn_timer = ENEMY_SPAWN_DELAY

        for item in self.inventory:
            self.inventory[item] = 0
        self.inventory['Cannonballs'] = PLAYER_AMMO_START
        self._update_ammo_hud()

        self.health = 100
        self._update_health_bar()

        self.ship_pos     = LVector3f(0, -38, 0)
        self.ship_heading = -90.0
        self.ship_speed   = 0.0
        self.cam_yaw      = 270.0
        self.ship_np.setPos(self.ship_pos.x, self.ship_pos.y, 0)
        self.ship_np.setH(self.ship_heading)
        self.bob_np.setHpr(0, 0, 0)

    def _update_health_bar(self):
        pct = max(0.0, self.health / 100.0)
        w   = max(0.002, _HP_BAR_W * pct)
        self.hp_bar['frameSize']  = (0, w, 0, _HP_BAR_H)
        r = min(1.0, 2.0 * (1.0 - pct))
        g = min(1.0, 2.0 * pct)
        self.hp_bar['frameColor'] = (r, g, 0.05, 0.92)
        self.hp_label.setText(str(self.health))
        if getattr(self, 'inv_open', False):
            self._refresh_inventory()

    # ------------------------------------------------------------------

    def _setup_economy(self):
        self.gold            = PLAYER_GOLD_START
        self.inventory       = {item: 0 for item in ITEMS}
        self.inventory['Cannonballs'] = PLAYER_AMMO_START
        self.docked          = False
        self.near_port_idx   = -1
        self.active_port_idx = -1
        self.trade_tab       = 'buy'
        self.trade_filter    = 'All'

        # ── Ammo HUD ─────────────────────────────────────────────────────
        self.ammo_hud = OnscreenText(
            text=self._ammo_hud_text(), pos=(-1.55, -0.88),
            scale=0.055, fg=(1.0, 0.90, 0.3, 1), shadow=(0, 0, 0, 0.85),
            align=TextNode.ALeft, mayChange=True,
        )

        # ── Action indicators (bottom-left, red) ─────────────────────────
        _akw = dict(scale=0.050, fg=(0.95, 0.22, 0.22, 1),
                    shadow=(0, 0, 0, 0.85), align=TextNode.ALeft)
        OnscreenText(text='[LMB] Aim+  [RMB] Aim-  [Space] Cannon', pos=(-1.55, -0.76), **_akw)
        OnscreenText(text='[F] Sea Mine',                            pos=(-1.55, -0.82), **_akw)

        # ── Bottom-right key hints ────────────────────────────────────────
        _kw = dict(scale=0.048, fg=(1.0, 0.88, 0.55, 1),
                   shadow=(0, 0, 0, 0.75), align=TextNode.ARight)
        _x  = 1.55
        OnscreenText(text='[M] Map',       pos=(_x, -0.72), **_kw)
        OnscreenText(text='[I] Inventory', pos=(_x, -0.78), **_kw)
        OnscreenText(text='[ESC] Menu',    pos=(_x, -0.84), **_kw)
        self.dock_prompt = OnscreenText(
            text='', pos=(_x, -0.90), mayChange=True, **_kw)
        self.dock_prompt.hide()

        # ── Trade panel ───────────────────────────────────────────────────
        self.trade_panel = DirectFrame(
            parent=self.aspect2d,
            frameColor=(0.04, 0.10, 0.25, 0.96),
            frameSize=(-0.82, 0.82, -0.72, 0.72),
            pos=(0, 0, 0),
        )
        self.trade_panel.hide()

        self.port_title = OnscreenText(
            text='', pos=(0, 0.60), scale=0.070,
            fg=(1.0, 0.85, 0.3, 1), shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter, parent=self.trade_panel, mayChange=True,
        )

        # Stats row: gold | cargo | ammo
        self.gold_label = OnscreenText(
            text='', pos=(-0.72, 0.47), scale=0.050,
            fg=(1.0, 0.85, 0.2, 1), shadow=(0, 0, 0, 0.85),
            align=TextNode.ALeft, parent=self.trade_panel, mayChange=True,
        )
        self.cargo_label = OnscreenText(
            text='', pos=(-0.08, 0.47), scale=0.050,
            fg=(0.8, 0.95, 1.0, 1), shadow=(0, 0, 0, 0.85),
            align=TextNode.ACenter, parent=self.trade_panel, mayChange=True,
        )
        self.ammo_label = OnscreenText(
            text='', pos=(0.72, 0.47), scale=0.050,
            fg=(1.0, 0.80, 0.3, 1), shadow=(0, 0, 0, 0.85),
            align=TextNode.ARight, parent=self.trade_panel, mayChange=True,
        )

        # ── Tabs ──────────────────────────────────────────────────────────
        self.tab_btns = {}
        for label, x in [('BUY', -0.15), ('SELL', 0.15)]:
            key = label.lower()
            btn = DirectButton(
                parent=self.trade_panel,
                text=label, text_scale=0.050,
                frameSize=(-0.13, 0.13, -0.048, 0.062),
                frameColor=_COL_TAB_ACTIVE if key == 'buy' else _COL_TAB_INACTIVE,
                pos=(x, 0, 0.36),
                command=self._set_tab, extraArgs=[key],
                relief=1,
            )
            self.tab_btns[key] = btn

        # ── Category filters ──────────────────────────────────────────────
        self.filter_btns = {}
        for label, x in [('All', -0.55), ('Goods', -0.20), ('Repairs', 0.18), ('Ammo', 0.54)]:
            btn = DirectButton(
                parent=self.trade_panel,
                text=label, text_scale=0.042,
                frameSize=(-0.15, 0.15, -0.040, 0.052),
                frameColor=_COL_FILT_ACTIVE if label == 'All' else _COL_FILT_INACTIVE,
                pos=(x, 0, 0.25),
                command=self._set_filter, extraArgs=[label],
                relief=1,
            )
            self.filter_btns[label] = btn

        # Column headers — use same x constants as row slots
        HDR_Z = 0.155
        OnscreenText(text='Item',  pos=(_TC_ITEM,  HDR_Z), scale=0.044,
                     fg=(0.65, 0.78, 1.0, 1), shadow=(0,0,0,0.7),
                     align=TextNode.ALeft,   parent=self.trade_panel, mayChange=False)
        OnscreenText(text='Price', pos=(_TC_PRICE, HDR_Z), scale=0.044,
                     fg=(0.65, 0.78, 1.0, 1), shadow=(0,0,0,0.7),
                     align=TextNode.ACenter, parent=self.trade_panel, mayChange=False)
        OnscreenText(text='Have',  pos=(_TC_HAVE,  HDR_Z), scale=0.044,
                     fg=(0.65, 0.78, 1.0, 1), shadow=(0,0,0,0.7),
                     align=TextNode.ACenter, parent=self.trade_panel, mayChange=False)

        # ── Row slots ─────────────────────────────────────────────────────
        self.row_slots = []
        for i in range(8):
            z = 0.06 - i * 0.095
            slot = {
                'name': OnscreenText(
                    text='', pos=(_TC_ITEM, z), scale=0.050,
                    fg=(1, 1, 1, 1), shadow=(0,0,0,0.7),
                    align=TextNode.ALeft, parent=self.trade_panel, mayChange=True,
                ),
                'price': OnscreenText(
                    text='', pos=(_TC_PRICE, z), scale=0.050,
                    fg=(1, 1, 1, 1), shadow=(0,0,0,0.7),
                    align=TextNode.ACenter, parent=self.trade_panel, mayChange=True,
                ),
                'have': OnscreenText(
                    text='', pos=(_TC_HAVE, z), scale=0.050,
                    fg=(0.8, 0.95, 1.0, 1), shadow=(0,0,0,0.7),
                    align=TextNode.ACenter, parent=self.trade_panel, mayChange=True,
                ),
                'btn': DirectButton(
                    parent=self.trade_panel,
                    text='', text_scale=0.042,
                    frameSize=(-0.115, 0.115, -0.038, 0.052),
                    frameColor=(0.2, 0.5, 0.9, 1),
                    pos=(_TC_BTN, 0, z + 0.008),
                    command=None, relief=1,
                ),
            }
            self.row_slots.append(slot)
            self._slot_hide(slot)

        DirectButton(
            parent=self.trade_panel,
            text='Leave Port', text_scale=0.050,
            frameSize=(-0.20, 0.20, -0.052, 0.065),
            frameColor=(0.60, 0.18, 0.10, 1),
            pos=(0, 0, -0.635),
            command=self._undock, relief=1,
        )

        self.accept('e', self._dock_toggle)

    def _ammo_hud_text(self):
        cb = self.inventory.get('Cannonballs', 0) if hasattr(self, 'inventory') else PLAYER_AMMO_START
        sm = self.inventory.get('Sea Mines', 0)   if hasattr(self, 'inventory') else 0
        return f'Cannonballs: {cb}   Sea Mines: {sm}'

    def _update_ammo_hud(self):
        self.ammo_hud.setText(self._ammo_hud_text())

    @staticmethod
    def _slot_hide(slot):
        for key in ('name', 'price', 'have'):
            slot[key].setText('')
        slot['btn']['text']        = ''
        slot['btn']['frameColor']  = (0, 0, 0, 0)
        slot['btn']['command']     = None
        slot['btn'].unbind(DGG.ENTER)
        slot['btn'].unbind(DGG.EXIT)

    def _populate_slot(self, slot, item, tab, port):
        slot['name'].setText(item)
        slot['have'].setText(str(self.inventory.get(item, 0)))
        if tab == 'buy':
            price = ITEM_PRICE[item]
            slot['price'].setText(f'{price}g')
            slot['price']['fg'] = (0.95, 0.78, 0.25, 1)
            cargo    = sum(qty for it, qty in self.inventory.items() if ITEMS[it]['cargo'])
            can_fit  = not ITEMS[item]['cargo'] or cargo < MAX_CARGO
            slot['btn']['text']       = 'Buy'
            slot['btn']['frameColor'] = (0.18, 0.48, 0.92, 1) if can_fit else (0.10, 0.15, 0.28, 1)
            slot['btn']['command']    = self._buy
            slot['btn']['extraArgs']  = [item]
        else:
            price = _port_buy_price(item, port)
            fg    = (0.35, 0.90, 0.35, 1) if item in port['sells'] else (0.90, 0.70, 0.30, 1)
            slot['price'].setText(f'{price}g')
            slot['price']['fg']       = fg
            slot['btn']['text']       = 'Sell'
            slot['btn']['frameColor'] = (0.18, 0.62, 0.28, 1)
            slot['btn']['command']    = self._sell
            slot['btn']['extraArgs']  = [item]
        info = ITEMS[item]
        if 'heal' in info or 'dmg' in info:
            slot['btn'].bind(DGG.ENTER, self._show_tooltip, extraArgs=[item])
            slot['btn'].bind(DGG.EXIT,  self._hide_tooltip)
        else:
            slot['btn'].unbind(DGG.ENTER)
            slot['btn'].unbind(DGG.EXIT)

    def _visible_items(self):
        port = PORTS[self.active_port_idx]
        filt = self.trade_filter

        def match(item):
            return filt == 'All' or ITEMS[item]['cat'] == filt

        if self.trade_tab == 'buy':
            return [item for item in port['sells'] if match(item)]
        else:
            return [item for item, qty in self.inventory.items()
                    if qty > 0 and match(item)]

    def _refresh_trade_ui(self):
        port  = PORTS[self.active_port_idx]
        items = self._visible_items()
        cargo = sum(qty for it, qty in self.inventory.items() if ITEMS[it]['cargo'])
        cb    = self.inventory.get('Cannonballs', 0)
        sm    = self.inventory.get('Sea Mines',   0)
        self.gold_label.setText(f'Gold: {self.gold}')
        self.cargo_label.setText(f'Cargo: {cargo}/{MAX_CARGO}')
        self.ammo_label.setText(f'Ammo: {cb}cb / {sm}sm')
        for i, slot in enumerate(self.row_slots):
            if i < len(items):
                self._populate_slot(slot, items[i], self.trade_tab, port)
            else:
                self._slot_hide(slot)

    def _set_tab(self, tab):
        self.trade_tab = tab
        for key, btn in self.tab_btns.items():
            btn['frameColor'] = _COL_TAB_ACTIVE if key == tab else _COL_TAB_INACTIVE
        self._refresh_trade_ui()

    def _set_filter(self, filt):
        self.trade_filter = filt
        for key, btn in self.filter_btns.items():
            btn['frameColor'] = _COL_FILT_ACTIVE if key == filt else _COL_FILT_INACTIVE
        self._refresh_trade_ui()

    def _dock_toggle(self):
        if self.near_port_idx >= 0 and not self.docked:
            self._dock()
        elif self.docked:
            self._undock()

    def _dock(self):
        self.docked          = True
        self.active_port_idx = self.near_port_idx
        self.trade_tab       = 'buy'
        self.trade_filter    = 'All'
        self.ship_speed      = 0.0
        self.dock_prompt.hide()
        self.fullmap_np.hide()
        for key, btn in self.tab_btns.items():
            btn['frameColor'] = _COL_TAB_ACTIVE if key == 'buy' else _COL_TAB_INACTIVE
        for key, btn in self.filter_btns.items():
            btn['frameColor'] = _COL_FILT_ACTIVE if key == 'All' else _COL_FILT_INACTIVE
        self.port_title.setText(f'PORT: {PORTS[self.active_port_idx]["name"].upper()}')
        self._refresh_trade_ui()
        self.trade_panel.show()
        props = WindowProperties()
        props.setCursorHidden(False)
        self.win.requestProperties(props)

    def _undock(self):
        self.docked = False
        self.trade_panel.hide()
        self.inv_open = False
        self.inv_panel.hide()
        self.tooltip.hide()
        props = WindowProperties()
        props.setCursorHidden(True)
        self.win.requestProperties(props)
        w = self.win.getProperties().getXSize()
        h = self.win.getProperties().getYSize()
        self.win.movePointer(0, w // 2, h // 2)
        if self.near_port_idx >= 0:
            self.dock_prompt.show()

    def _buy(self, item):
        price     = ITEM_PRICE[item]
        cargo     = sum(qty for it, qty in self.inventory.items() if ITEMS[it]['cargo'])
        can_fit   = not ITEMS[item]['cargo'] or cargo < MAX_CARGO
        if self.gold >= price and can_fit:
            self.gold -= price
            self.inventory[item] += 1
            if self.snd_gold: self.snd_gold.play()
            self._update_ammo_hud()
            self._refresh_trade_ui()

    def _sell(self, item):
        if self.inventory.get(item, 0) <= 0:
            return
        self.gold += _port_buy_price(item, PORTS[self.active_port_idx])
        self.inventory[item] -= 1
        if self.snd_gold: self.snd_gold.play()
        self._update_ammo_hud()
        self._refresh_trade_ui()

    def _update_economy(self, dt):
        prev_idx           = self.near_port_idx
        self.near_port_idx = -1
        for i, port in enumerate(PORTS):
            dx = self.ship_pos.x - port['pos'].x
            dy = self.ship_pos.y - port['pos'].y
            if math.sqrt(dx*dx + dy*dy) < port['trigger_r']:
                self.near_port_idx = i
                break

        if self.near_port_idx >= 0 and prev_idx < 0 and not self.docked:
            self.dock_prompt.setText('[E] Dock')
            self.dock_prompt.show()
        elif self.near_port_idx < 0 and prev_idx >= 0:
            self.dock_prompt.hide()
            if self.docked:
                self._undock()


    # ------------------------------------------------------------------
    # Tooltip
    # ------------------------------------------------------------------

    def _setup_tooltip(self):
        self.tooltip = DirectFrame(
            parent=self.aspect2d,
            frameSize=(-0.42, 0.42, -0.035, 0.055),
            frameColor=(0.06, 0.06, 0.06, 0.90),
            pos=(0, 0, -0.80),
        )
        self.tooltip_text = OnscreenText(
            parent=self.tooltip, text='', pos=(0, 0),
            scale=0.047, fg=(1.0, 0.88, 0.45, 1),
            align=TextNode.ACenter, mayChange=True,
        )
        self.tooltip.hide()

    def _show_tooltip(self, item, _=None):
        info = ITEMS[item]
        if 'heal' in info:
            txt = f'{item}  \u2014  Restores +{info["heal"]} HP'
        elif 'dmg' in info:
            txt = f'{item}  \u2014  Deals {info["dmg"]} damage'
        else:
            return
        self.tooltip_text.setText(txt)
        self.tooltip.show()

    def _hide_tooltip(self, _=None):
        self.tooltip.hide()

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------

    def _setup_inventory(self):
        self.inv_open = False
        self.inv_panel = DirectFrame(
            parent=self.aspect2d,
            frameColor=(0.04, 0.10, 0.25, 0.96),
            frameSize=(-0.82, 0.82, -0.72, 0.72),
            pos=(0, 0, 0),
        )
        self.inv_panel.hide()

        OnscreenText(
            text='INVENTORY', pos=(0, 0.60), scale=0.070,
            fg=(1.0, 0.85, 0.3, 1), shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter, parent=self.inv_panel, mayChange=False,
        )
        OnscreenText(
            text='[I] Close', pos=(0, 0.50), scale=0.042,
            fg=(0.65, 0.78, 1.0, 0.8), shadow=(0, 0, 0, 0.7),
            align=TextNode.ACenter, parent=self.inv_panel, mayChange=False,
        )

        HDR_Z = 0.38
        OnscreenText(text='Item',     pos=(_IC_ITEM, HDR_Z), scale=0.044,
                     fg=(0.65, 0.78, 1.0, 1), shadow=(0,0,0,0.7),
                     align=TextNode.ALeft,   parent=self.inv_panel, mayChange=False)
        OnscreenText(text='Have',     pos=(_IC_HAVE, HDR_Z), scale=0.044,
                     fg=(0.65, 0.78, 1.0, 1), shadow=(0,0,0,0.7),
                     align=TextNode.ACenter, parent=self.inv_panel, mayChange=False)
        OnscreenText(text='Action',   pos=(_IC_BTN,  HDR_Z), scale=0.044,
                     fg=(0.65, 0.78, 1.0, 1), shadow=(0,0,0,0.7),
                     align=TextNode.ACenter, parent=self.inv_panel, mayChange=False)

        self.inv_slots = []
        for i, item in enumerate(ITEMS):
            z = 0.28 - i * 0.086
            slot = {
                'item': item,
                'name': OnscreenText(
                    text='', pos=(_IC_ITEM, z), scale=0.050,
                    fg=(1, 1, 1, 1), shadow=(0,0,0,0.7),
                    align=TextNode.ALeft, parent=self.inv_panel, mayChange=True,
                ),
                'have': OnscreenText(
                    text='', pos=(_IC_HAVE, z), scale=0.050,
                    fg=(0.8, 0.95, 1.0, 1), shadow=(0,0,0,0.7),
                    align=TextNode.ACenter, parent=self.inv_panel, mayChange=True,
                ),
                'btn': DirectButton(
                    parent=self.inv_panel,
                    text='', text_scale=0.042,
                    frameSize=(-0.13, 0.13, -0.038, 0.052),
                    frameColor=(0, 0, 0, 0),
                    pos=(_IC_BTN, 0, z + 0.008),
                    command=None, relief=1,
                ),
            }
            self.inv_slots.append(slot)

    def _refresh_inventory(self):
        for slot in self.inv_slots:
            item = slot['item']
            qty  = self.inventory.get(item, 0)
            slot['name'].setText(item)
            slot['have'].setText(str(qty))
            info = ITEMS[item]
            if info['cat'] == 'Repairs':
                slot['btn']['text']       = 'Use'
                can_use = qty > 0 and self.health < 100
                slot['btn']['frameColor'] = (0.65, 0.35, 0.08, 1) if can_use else (0.25, 0.18, 0.08, 1)
                slot['btn']['command']    = self._use_item if can_use else None
                slot['btn']['extraArgs']  = [item]
                slot['btn'].bind(DGG.ENTER, self._show_tooltip, extraArgs=[item])
                slot['btn'].bind(DGG.EXIT,  self._hide_tooltip)
            elif info['cat'] == 'Ammo':
                slot['btn']['text']       = f'DMG {info["dmg"]}'
                slot['btn']['frameColor'] = (0.30, 0.10, 0.10, 0.75)
                slot['btn']['command']    = None
                slot['btn']['extraArgs']  = []
                slot['btn'].bind(DGG.ENTER, self._show_tooltip, extraArgs=[item])
                slot['btn'].bind(DGG.EXIT,  self._hide_tooltip)
            else:
                slot['btn']['text']       = ''
                slot['btn']['frameColor'] = (0, 0, 0, 0)
                slot['btn']['command']    = None
                slot['btn']['extraArgs']  = []
                slot['btn'].unbind(DGG.ENTER)
                slot['btn'].unbind(DGG.EXIT)

    def _use_item(self, item):
        if self.inventory.get(item, 0) <= 0 or self.health >= 100:
            return
        self.inventory[item] -= 1
        self.health = min(100, self.health + ITEMS[item]['heal'])
        self._update_health_bar()
        self._refresh_inventory()
        if self.docked:
            self._refresh_trade_ui()

    def _toggle_inventory(self):
        if self.inv_panel.isHidden():
            self.inv_open = True
            self._refresh_inventory()
            self.inv_panel.show()
            props = WindowProperties()
            props.setCursorHidden(False)
            self.win.requestProperties(props)
        else:
            self.inv_open = False
            self.inv_panel.hide()
            self.tooltip.hide()
            if not self.docked:
                props = WindowProperties()
                props.setCursorHidden(True)
                self.win.requestProperties(props)
                w = self.win.getProperties().getXSize()
                h = self.win.getProperties().getYSize()
                self.win.movePointer(0, w // 2, h // 2)


if __name__ == '__main__':
    PirateGame().run()

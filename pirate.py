import math, os
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from direct.gui.DirectGui import DirectFrame, DirectButton, DGG
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    GeomTriangles, Geom, GeomNode,
    LVector3f, LColor,
    AmbientLight, DirectionalLight,
    LineSegs, WindowProperties, TextNode,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_SPEED    = 55.0
TURN_SPEED   = 80.0
ACCELERATION = 50.0
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
CANNON_CHARGE_T  = 2.0
CANNON_GRAVITY   = -28.0
CANNON_Z         = 3.0

WORLD_RANGE = 900.0
MINI_HALF   = 0.16
FULL_HALF   = 0.75

ASSETS     = os.path.join(os.path.dirname(__file__), 'assets')
MODELS_DIR = os.path.join(ASSETS, 'models', 'OBJ')
SHIP_MODEL = os.path.join(MODELS_DIR, 'ship-large.obj')
BALL_MODEL = os.path.join(MODELS_DIR, 'cannon-ball.obj')

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
        'pos': LVector3f(-350, 280, 0),
        'radius': 35.0,
        'trigger_r': 48.0,
        'sells': {'Cannonballs', 'Sea Mines', 'Food'},
    },
    {
        'name': 'Palm Cove',
        'pos': LVector3f(120, -440, 0),
        'radius': 28.0,
        'trigger_r': 40.0,
        'sells': {'Coconuts', 'Fruit', 'Rum'},
    },
    {
        'name': "Shipwright's Cove",
        'pos': LVector3f(-220, -320, 0),
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
_HP_BAR_W    = 0.36
_HP_BAR_H    = 0.040
_HP_BAR_X    = -1.50
_HP_BAR_Z    = -0.95


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _make_ocean(size=900):
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


def _make_landing_ring(r=3.5, n=20):
    ls = LineSegs('landing_ring')
    ls.setColor(1.0, 0.35, 0.05, 1.0)
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

        self.setBackgroundColor(0.40, 0.68, 0.92, 1)

        props = WindowProperties()
        props.setCursorHidden(True)
        props.setFullscreen(True)
        self.win.requestProperties(props)

        self._setup_lighting()
        self._setup_ocean()
        self._setup_ship()
        self._setup_islands()
        self._setup_keys()
        self._setup_aim()
        self._setup_maps()
        self._setup_economy()
        self._setup_hud()
        self._setup_tooltip()
        self._setup_inventory()

        self.taskMgr.add(self._update, 'update')
        self.accept('escape', self.userExit)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_lighting(self):
        sun = DirectionalLight('sun')
        sun.setColor(LColor(1.0, 0.95, 0.85, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(45, -50, 0)
        self.render.setLight(sun_np)
        amb = AmbientLight('amb')
        amb.setColor(LColor(0.45, 0.48, 0.55, 1))
        self.render.setLight(self.render.attachNewNode(amb))

    def _setup_ocean(self):
        self.render.attachNewNode(_make_ocean())
        self.render.attachNewNode(_make_ocean_grid())

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

        self.ship_np.setPos(self.ship_pos)
        self.camLens.setFov(70)

    def _setup_islands(self):
        def place_all(port, pieces):
            np = self.render.attachNewNode(f'island_{port["name"]}')
            np.setPos(port['pos'])
            for fname, ox, oy, oz, h, scale in pieces:
                p = os.path.join(MODELS_DIR, fname)
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
        self.charging    = False
        self.charge_time = 0.0
        self.projectiles = []

        self.target_np = self.render.attachNewNode(_make_landing_ring())
        self.target_np.hide()

        self.accept('mouse1',    self._charge_start)
        self.accept('mouse1-up', self._fire)

    def _charge_start(self):
        if self.docked:
            return
        self.charging    = True
        self.charge_time = 0.0

    def _fire(self):
        if not self.charging:
            return
        self.charging = False
        if self.inventory.get('Cannonballs', 0) <= 0:
            return

        self.inventory['Cannonballs'] -= 1
        self._update_ammo_hud()

        frac   = self.charge_time / CANNON_CHARGE_T
        land_d = CANNON_MIN_RANGE + frac * (CANNON_MAX_RANGE - CANNON_MIN_RANGE)
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
        self.projectiles.append({
            'np':  ball_np,
            'pos': LVector3f(self.ship_pos.x, self.ship_pos.y, CANNON_Z),
            'vel': LVector3f(fdx * CANNON_SPEED, fdy * CANNON_SPEED, vz),
        })

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def _update(self, task):
        dt = globalClock.getDt()
        self._update_ship(dt)
        self._update_camera()
        self._update_aim(dt)
        self._update_projectiles(dt)
        self._update_mines(dt)
        self._update_minimap()
        self._update_economy(dt)
        return Task.cont

    def _update_ship(self, dt):
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
        yr  = math.radians(self.cam_yaw)
        fdx = -math.sin(yr)
        fdy = -math.cos(yr)

        if self.charging:
            self.charge_time = min(self.charge_time + dt, CANNON_CHARGE_T)
            frac   = self.charge_time / CANNON_CHARGE_T
            land_d = CANNON_MIN_RANGE + frac * (CANNON_MAX_RANGE - CANNON_MIN_RANGE)
            self.target_np.setPos(
                self.ship_pos.x + fdx * land_d,
                self.ship_pos.y + fdy * land_d,
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
            if p['pos'].z > -1.0:
                p['np'].setPos(p['pos'])
                alive.append(p)
            else:
                p['np'].removeNode()
        self.projectiles = alive

    def _setup_maps(self):
        a2d = self.aspect2d
        ms  = MINI_HALF / WORLD_RANGE
        fs  = FULL_HALF / WORLD_RANGE

        ar  = self.getAspectRatio()
        self.mini_cx = ar - MINI_HALF - 0.03
        self.mini_cz = 1.0 - MINI_HALF - 0.03
        MCX, MCZ = self.mini_cx, self.mini_cz

        # ── Minimap ───────────────────────────────────────────────────────
        DirectFrame(parent=a2d,
                    frameColor=(0.03, 0.10, 0.25, 0.82),
                    frameSize=(-MINI_HALF, MINI_HALF, -MINI_HALF, MINI_HALF),
                    pos=(MCX, 0, MCZ))

        bls = LineSegs()
        bls.setColor(0.50, 0.62, 0.85, 1); bls.setThickness(1.5)
        h = MINI_HALF
        bls.moveTo(MCX-h, 0, MCZ-h)
        for dx, dz in [(h,-h),(h,h),(-h,h),(-h,-h)]:
            bls.drawTo(MCX+dx, 0, MCZ+dz)
        a2d.attachNewNode(bls.create())

        for port in PORTS:
            ix = MCX + port['pos'].x * ms
            iz = MCZ + port['pos'].y * ms
            DirectFrame(parent=a2d, frameColor=(0.45, 0.88, 0.32, 1),
                        frameSize=(-0.009, 0.009, -0.009, 0.009),
                        pos=(ix, 0, iz))
            OnscreenText(text=port['name'], pos=(ix, iz + 0.022),
                         scale=0.028, fg=(0.65, 1.0, 0.45, 1),
                         shadow=(0,0,0,0.85), align=TextNode.ACenter)

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
        ms  = MINI_HALF / WORLD_RANGE
        MCX, MCZ = self.mini_cx, self.mini_cz
        mx  = MCX + self.ship_pos.x * ms
        mz  = MCZ + self.ship_pos.y * ms
        mx  = max(MCX - MINI_HALF + 0.012, min(MCX + MINI_HALF - 0.012, mx))
        mz  = max(MCZ - MINI_HALF + 0.012, min(MCZ + MINI_HALF - 0.012, mz))
        self.mini_player.setPos(mx, 0, mz)
        self.mini_player.setP(-self.ship_heading)

        if not self.fullmap_np.isHidden():
            fs  = FULL_HALF / WORLD_RANGE
            fx  = max(-FULL_HALF + 0.025, min(FULL_HALF - 0.025, self.ship_pos.x * fs))
            fz  = max(-FULL_HALF + 0.025, min(FULL_HALF - 0.025, self.ship_pos.y * fs))
            self.full_player.setPos(fx, 0, fz)
            self.full_player.setP(-self.ship_heading)

    def _update_camera(self):
        if self.docked or self.inv_open:
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
        self.health = 100
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
        p = os.path.join(MODELS_DIR, 'barrel.obj')
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
            # Collision
            dx = self.ship_pos.x - mine['pos'].x
            dy = self.ship_pos.y - mine['pos'].y
            if math.sqrt(dx*dx + dy*dy) < MINE_RADIUS:
                mine['np'].removeNode()
                self._take_damage(50)
            else:
                alive.append(mine)
        self.mines = alive

    def _take_damage(self, amount):
        self.health = max(0, self.health - amount)
        self._update_health_bar()
        if self.health <= 0:
            self._die()

    def _die(self):
        if self.docked:
            self._undock()

        # Reset inventory to starting state
        for item in self.inventory:
            self.inventory[item] = 0
        self.inventory['Cannonballs'] = PLAYER_AMMO_START
        self._update_ammo_hud()

        # Restore health
        self.health = 100
        self._update_health_bar()

        # Respawn at Tortuga dock
        self.ship_pos     = LVector3f(0, -38, 0)
        self.ship_heading = -90.0
        self.ship_speed   = 0.0
        self.cam_yaw      = 270.0
        self.ship_np.setPos(self.ship_pos)
        self.ship_np.setH(self.ship_heading)

        # Brief on-screen notice
        msg = OnscreenText(
            text='Ship sunk!  Respawning at Tortuga...',
            pos=(0, 0.15), scale=0.075,
            fg=(1.0, 0.30, 0.30, 1), shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter, mayChange=False,
        )
        self.taskMgr.doMethodLater(2.5, lambda t: msg.destroy(), 'death_msg')

    def _update_health_bar(self):
        pct = max(0.0, self.health / 100.0)
        w   = max(0.002, _HP_BAR_W * pct)
        self.hp_bar['frameSize']  = (0, w, 0, _HP_BAR_H)
        r = min(1.0, 2.0 * (1.0 - pct))
        g = min(1.0, 2.0 * pct)
        self.hp_bar['frameColor'] = (r, g, 0.05, 0.92)
        self.hp_label.setText(str(self.health))

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

        # ── Dock prompt ───────────────────────────────────────────────────
        self.dock_prompt = OnscreenText(
            text='[E] Dock', pos=(0, -0.82), scale=0.07,
            fg=(1.0, 0.95, 0.5, 1), shadow=(0, 0, 0, 0.9),
            align=TextNode.ACenter, mayChange=True,
        )
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
            self._update_ammo_hud()
            self._refresh_trade_ui()

    def _sell(self, item):
        if self.inventory.get(item, 0) <= 0:
            return
        self.gold += _port_buy_price(item, PORTS[self.active_port_idx])
        self.inventory[item] -= 1
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
            self.dock_prompt.setText(f'[E] Dock at {PORTS[self.near_port_idx]["name"]}')
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
                slot['btn']['frameColor'] = (0.65, 0.35, 0.08, 1) if qty > 0 else (0.25, 0.18, 0.08, 1)
                slot['btn']['command']    = self._use_item if qty > 0 else None
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

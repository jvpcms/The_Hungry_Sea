import math, os
from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from panda3d.core import (
    GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    GeomTriangles, Geom, GeomNode,
    LVector3f, LColor,
    AmbientLight, DirectionalLight,
    LineSegs, WindowProperties,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_SPEED    = 25.0   # units / sec
TURN_SPEED   = 80.0   # degrees / sec
ACCELERATION = 18.0   # units / sec²
DRAG         = 2.2    # speed lost per second proportional to current speed
CAM_DIST      = 110.0
CAM_PITCH_MIN =   5.0   # degrees above horizon
CAM_PITCH_MAX =  75.0
MOUSE_SENS_H  =  80.0   # degrees per normalized mouse unit
MOUSE_SENS_V  =  50.0

PITCH_AMPLITUDE = 2.5   # degrees, front-to-back (slower)
PITCH_PERIOD    = 7.0
ROLL_AMPLITUDE  = 4.0   # degrees, side-to-side (faster)
ROLL_PERIOD     = 5.0
HULL_DRAFT      = 4.0   # world units keel sits below waterline

CANNON_SPEED     = 50.0   # horizontal units / sec
CANNON_MAX_RANGE = 130.0
CANNON_MIN_RANGE = 15.0
CANNON_CHARGE_T  = 2.0    # seconds to reach max range
CANNON_GRAVITY   = -28.0  # z acceleration for projectile
CANNON_Z         = 3.0    # launch height above waterline

ASSETS     = os.path.join(os.path.dirname(__file__), 'assets')
MODELS_DIR = os.path.join(ASSETS, 'models', 'OBJ')
SHIP_MODEL = os.path.join(MODELS_DIR, 'ship-large.obj')
BALL_MODEL = os.path.join(MODELS_DIR, 'cannon-ball.obj')


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
    """Elongated box pointing in +Y (forward in Panda3D local space)."""
    fmt   = GeomVertexFormat.getV3c4()
    vdata = GeomVertexData('ship', fmt, Geom.UHStatic)
    hw, hl, hh = 1.5, 5.0, 1.2   # half-width, half-length, half-height
    verts = [
        (-hw, -hl, -hh), ( hw, -hl, -hh), ( hw,  hl, -hh), (-hw,  hl, -hh),
        (-hw, -hl,  hh), ( hw, -hl,  hh), ( hw,  hl,  hh), (-hw,  hl,  hh),
    ]
    faces = [
        (0,1,2,3), (7,6,5,4), (0,4,5,1),
        (2,6,7,3), (0,3,7,4), (1,5,6,2),
    ]
    colors = [
        (0.55, 0.35, 0.18, 1),  # bottom
        (0.65, 0.42, 0.22, 1),  # top
        (0.50, 0.30, 0.15, 1),  # sides
        (0.50, 0.30, 0.15, 1),
        (0.45, 0.28, 0.14, 1),
        (0.45, 0.28, 0.14, 1),
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

        self.ship_pos     = LVector3f(0, 0, 0)
        self.ship_heading = 0.0    # degrees; 0 = facing +Y
        self.ship_speed   = 0.0
        self.cam_yaw      = 180.0  # world-space angle: 180 = camera behind ship
        self.cam_pitch    = 15.0   # degrees above horizon

        self.setBackgroundColor(0.40, 0.68, 0.92, 1)

        props = WindowProperties()
        props.setCursorHidden(True)
        self.win.requestProperties(props)

        self._setup_lighting()
        self._setup_ocean()
        self._setup_ship()
        self._setup_keys()
        self._setup_aim()

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
        self.bob_np  = self.ship_np.attachNewNode('bob')  # pivot sits at waterline z=0

        if os.path.exists(SHIP_MODEL):
            print(f'Loading ship model: {SHIP_MODEL}')
            model = self.loader.loadModel(SHIP_MODEL)
            model.reparentTo(self.bob_np)
            model.setHpr(90, 90, 90)
            model.setScale(3.0)
            model.setZ(-HULL_DRAFT)
        else:
            print('Ship model not found — using placeholder.')
            ph = self.bob_np.attachNewNode(_make_placeholder_ship())
            ph.setZ(-HULL_DRAFT)

        self.ship_np.setPos(self.ship_pos)
        self.camLens.setFov(70)

    def _setup_keys(self):
        self.keys = {'w': False, 's': False, 'a': False, 'd': False}
        for key in self.keys:
            self.accept(key,        self._key_down, [key])
            self.accept(f'{key}-up', self._key_up,  [key])

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
        self.charging    = True
        self.charge_time = 0.0

    def _fire(self):
        if not self.charging:
            return
        self.charging = False

        frac   = self.charge_time / CANNON_CHARGE_T
        land_d = CANNON_MIN_RANGE + frac * (CANNON_MAX_RANGE - CANNON_MIN_RANGE)
        yr     = math.radians(self.cam_yaw)
        fdx, fdy = -math.sin(yr), -math.cos(yr)

        t_f = land_d / CANNON_SPEED
        # vz so ball launched from CANNON_Z lands at z=0 after t_f seconds
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
        return Task.cont

    def _update_ship(self, dt):
        # Acceleration / braking
        if self.keys['w']:
            self.ship_speed += ACCELERATION * dt
        if self.keys['s']:
            self.ship_speed -= ACCELERATION * dt

        # Drag (always applied so ship coasts to a stop)
        self.ship_speed -= DRAG * self.ship_speed * dt
        self.ship_speed  = max(0.0, min(self.ship_speed, MAX_SPEED))

        # Turning — scaled by speed so slow ship turns less sharply
        turn_scale = 0.15 + 0.85 * (self.ship_speed / MAX_SPEED)
        if self.keys['a']:
            self.ship_heading += TURN_SPEED * turn_scale * dt
        if self.keys['d']:
            self.ship_heading -= TURN_SPEED * turn_scale * dt

        # Panda3D setH is CCW, so bow direction = (-sin H, cos H)
        rad = math.radians(self.ship_heading)
        self.ship_pos.x -= math.sin(rad) * self.ship_speed * dt
        self.ship_pos.y += math.cos(rad) * self.ship_speed * dt

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

    def _update_camera(self):
        if self.mouseWatcherNode.hasMouse():
            dx = self.mouseWatcherNode.getMouseX()
            dy = self.mouseWatcherNode.getMouseY()
            self.cam_yaw   += dx * MOUSE_SENS_H
            self.cam_pitch -= dy * MOUSE_SENS_V
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


if __name__ == '__main__':
    PirateGame().run()

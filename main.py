import struct, os, math, colorsys, json, random
import numpy as np

from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    GeomVertexData, GeomVertexFormat, GeomVertexWriter,
    GeomTriangles, Geom, GeomNode,
    LVector3f, LVector2f, LPoint3f, LQuaternionf, LMatrix4f,
    AmbientLight, DirectionalLight, Material, LColor, TextNode, Point3,
    LineSegs,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MESH_RADIUS  = 25.0
WORLD_SCALE  = 4.0
GLOBE_RADIUS = MESH_RADIUS * WORLD_SCALE   # 100.0

CAM_DIST     = 340.0   # orbit distance — globe fills ~40% of screen
DAY_DURATION = 180.0   # seconds for a full day/night cycle

COUNTRY_ROWS   = 1800  # 0.1° lat resolution
COUNTRY_COLS   = 3600  # 0.1° lon resolution
COUNTRY_DILATE = 25    # iterations of 8-connected expansion — fills country interiors

DEPLOY_DURATION = 30.0
FIGHT_DURATION  =  5.0
NUM_AI          =  2

OWNER_COLORS = {
    0: (0.50, 0.50, 0.50, 1),
    1: (0.20, 0.55, 1.00, 1),
    2: (1.00, 0.25, 0.25, 1),
    3: (1.00, 0.65, 0.10, 1),
}
SELECTED_COLOR = (0.55, 0.85, 1.00, 1)
TARGETED_COLOR = (1.00, 0.80, 0.20, 1)

COUNTRIES_PATH    = os.path.join(os.path.dirname(__file__), 'earth_model', 'Countries_High_Res.bytes')
OCEAN_PATH        = os.path.join(os.path.dirname(__file__), 'earth_model', 'Ocean.bytes')
COUNTRY_DATA_PATH = os.path.join(os.path.dirname(__file__), 'earth_model', 'country_data.json')


# ---------------------------------------------------------------------------
# Coordinate helpers
# ---------------------------------------------------------------------------

def latlon_to_pos(lat_deg, lon_deg):
    lat = math.radians(lat_deg)
    lon = math.radians(lon_deg)
    r   = math.cos(lat)
    return LVector3f(
        GLOBE_RADIUS * r * math.sin(lon),
        GLOBE_RADIUS * r * (-math.cos(lon)),
        GLOBE_RADIUS * math.sin(lat),
    )


def _compute_tangent_frame(pos):
    up   = LVector3f(pos).normalized()
    east = LVector3f(0, 0, 1).cross(up)
    if east.length() < 1e-4:
        east = LVector3f(0, 1, 0).cross(up)
    east.normalize()
    north = up.cross(east); north.normalize()
    return east, north


def _surface_quat(pos):
    sn   = LVector3f(pos).normalized()
    east = LVector3f(0, 0, 1).cross(sn)
    if east.length() < 1e-4:
        east = LVector3f(0, 1, 0).cross(sn)
    east.normalize()
    fwd = sn.cross(east); fwd.normalize()
    mat = LMatrix4f(
        east.x, east.y, east.z, 0,
        fwd.x,  fwd.y,  fwd.z,  0,
        sn.x,   sn.y,   sn.z,   0,
        0,      0,      0,      1,
    )
    q = LQuaternionf(); q.setFromMatrix(mat)
    return q


# ---------------------------------------------------------------------------
# Binary mesh parsers
# ---------------------------------------------------------------------------

def _parse_multi_mesh(path):
    with open(path, 'rb') as f:
        data = f.read()
    meshes, offset = [], 0
    while offset < len(data):
        if offset + 8 > len(data): break
        tb = struct.unpack_from('<i', data, offset)[0]
        if tb <= 0: break
        meshes.append(_read_mesh(data, offset))
        offset += tb
    return meshes


def _parse_single_mesh(path):
    with open(path, 'rb') as f:
        data = f.read()
    return _read_mesh(data, 0)


def _read_mesh(data, offset):
    name_len   = struct.unpack_from('<i', data, offset + 4)[0]
    name_bytes = data[offset + 8 : offset + 8 + name_len]
    name       = name_bytes.decode('utf-16-le')
    off        = offset + 8 + name_len
    vc  = struct.unpack_from('<i', data, off)[0]; off += 4
    rv  = struct.unpack_from(f'<{vc*3}f', data, off); off += vc * 12
    raw_verts = [(rv[i*3], rv[i*3+2], rv[i*3+1]) for i in range(vc)]
    verts = [
        (px * MESH_RADIUS / math.sqrt(px*px + py*py + pz*pz),
         py * MESH_RADIUS / math.sqrt(px*px + py*py + pz*pz),
         pz * MESH_RADIUS / math.sqrt(px*px + py*py + pz*pz))
        for (px, py, pz) in raw_verts
    ]
    normals = [(px/MESH_RADIUS, py/MESH_RADIUS, pz/MESH_RADIUS) for (px, py, pz) in verts]
    tic = struct.unpack_from('<i', data, off)[0]; off += 4
    idx = list(struct.unpack_from(f'<{tic}i', data, off)); off += tic * 4
    nc  = struct.unpack_from('<i', data, off)[0]; off += 4
    off += nc * 12  # skip binary normals; using position-derived normals above
    return {'name': name, 'verts': verts, 'normals': normals, 'indices': idx}


# ---------------------------------------------------------------------------
# Geometry builders
# ---------------------------------------------------------------------------

def _build_geom_from_meshes(meshes):
    total = sum(len(m['verts']) for m in meshes)
    fmt   = GeomVertexFormat.getV3n3()
    vdata = GeomVertexData('mesh', fmt, Geom.UHStatic)
    vdata.setNumRows(total)
    vw   = GeomVertexWriter(vdata, 'vertex')
    nw   = GeomVertexWriter(vdata, 'normal')
    tris = GeomTriangles(Geom.UHStatic)
    base = 0
    for m in meshes:
        for (px,py,pz),(nx,ny,nz) in zip(m['verts'], m['normals']):
            vw.addData3(px,py,pz); nw.addData3(nx,ny,nz)
        idx = m['indices']
        for t in range(0, len(idx), 3):
            tris.addVertices(idx[t]+base, idx[t+2]+base, idx[t+1]+base)
        base += len(m['verts'])
    g = Geom(vdata); g.addPrimitive(tris)
    gn = GeomNode('mesh'); gn.addGeom(g)
    return gn


def _build_outline_segs(meshes):
    """Draw boundary edges (appear in only 1 triangle) of each country mesh as black lines."""
    ls = LineSegs()
    ls.setThickness(2.0)
    ls.setColor(0, 0, 0, 1)
    s = 1.004  # raise slightly above country surfaces (setScale 1.003)
    for mesh in meshes:
        verts   = mesh['verts']
        idx     = mesh['indices']
        edge_ct = {}
        for t in range(0, len(idx), 3):
            for i in range(3):
                a, b = idx[t + i], idx[t + (i + 1) % 3]
                e = (min(a, b), max(a, b))
                edge_ct[e] = edge_ct.get(e, 0) + 1
        for (a, b), ct in edge_ct.items():
            if ct == 1:
                p0, p1 = verts[a], verts[b]
                ls.moveTo(p0[0] * s, p0[1] * s, p0[2] * s)
                ls.drawTo(p1[0] * s, p1[1] * s, p1[2] * s)
    return ls.create()


def _make_mat(diffuse, ambient, specular=LColor(0,0,0,1), shininess=8.0):
    m = Material()
    m.setDiffuse(diffuse)
    m.setAmbient(ambient)
    m.setSpecular(specular)
    m.setShininess(shininess)
    return m


# ---------------------------------------------------------------------------
# Game
# ---------------------------------------------------------------------------

def _load_country_data():
    with open(COUNTRY_DATA_PATH, encoding='utf-8') as f:
        return json.load(f)


class EarthGame(ShowBase):
    def __init__(self):
        super().__init__()

        self.country_data = _load_country_data()   # {name: {area_km2, population, power}}
        self.globe_root = self.render.attachNewNode('globe_root')
        self.globe_quat = LQuaternionf()
        self.dragging    = False
        self.last_mouse  = None
        self.drag_anchor = None   # world-space unit vector grabbed on mouse-down

        self._setup_camera()
        self._setup_lighting()
        self._setup_ocean()
        self._setup_globe()
        self._setup_grid_lines()
        self._build_adjacency()
        self._init_game_state()
        self._setup_game_ui()
        self._setup_mouse()
        self._setup_hover_ui()

        self.taskMgr.add(self._update, 'main-update')
        self.accept('escape', self.userExit)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_camera(self):
        self.disableMouse()
        self.camLens.setFov(45)
        self.camera.setPos(0, -CAM_DIST, 0)
        self.camera.lookAt(0, 0, 0)

    def _setup_lighting(self):
        sun = DirectionalLight('sun')
        sun.setColor(LColor(1.0, 0.95, 0.85, 1))
        self.sun_np = self.render.attachNewNode(sun)
        self.sun_np.setHpr(0, -35, 0)
        self.render.setLight(self.sun_np)

        al = AmbientLight('amb')
        al.setColor(LColor(0.38, 0.38, 0.44, 1))
        self.render.setLight(self.render.attachNewNode(al))

    def _setup_ocean(self):
        self.ocean_mesh = _parse_single_mesh(OCEAN_PATH)
        ocean_np = self.globe_root.attachNewNode(
            _build_geom_from_meshes([self.ocean_mesh]))
        ocean_np.setColor(0.08, 0.22, 0.48, 1)
        ocean_np.setLightOff()

    def _setup_globe(self):
        print('Loading country meshes...')
        meshes = _parse_multi_mesh(COUNTRIES_PATH)
        print(f'  {len(meshes)} meshes loaded.')

        self.country_nps = {}
        for mesh in meshes:
            country_np = self.globe_root.attachNewNode(
                _build_geom_from_meshes([mesh]))
            country_np.setScale(1.003)
            country_np.setColor(*OWNER_COLORS[0])
            country_np.setLightOff()
            self.country_nps[mesh['name']] = country_np

        self.globe_root.setScale(WORLD_SCALE)

        outline_np = self.globe_root.attachNewNode(_build_outline_segs(meshes))
        outline_np.setLightOff()

        print('Building country grid...')
        self._build_country_grid(meshes)
        print('  Done.')

    def _build_country_grid(self, meshes):
        self.country_names = ['']   # index 0 = ocean
        grid = np.zeros((COUNTRY_ROWS, COUNTRY_COLS), dtype=np.uint8)

        # Mark exact vertex cells
        for idx, mesh in enumerate(meshes, start=1):
            self.country_names.append(mesh['name'])
            for (px, py, pz) in mesh['verts']:
                r = math.sqrt(px*px + py*py + pz*pz)
                if r < 1e-6: continue
                lat = math.asin(max(-1.0, min(1.0, pz / r)))
                lon = math.atan2(px, -py)
                row = max(0, min(COUNTRY_ROWS-1,
                          int((lat + math.pi/2) / math.pi * COUNTRY_ROWS)))
                col = int((lon + math.pi) / (2*math.pi) * COUNTRY_COLS) % COUNTRY_COLS
                grid[row, col] = idx

        # Iterative 8-connected dilation using numpy shifts — fills country interiors
        # Each iteration expands filled cells by 1 in all 8 directions without
        # overwriting already-marked cells (preserves country borders).
        neighbors = [(-1,-1),(-1,0),(-1,1),(0,-1),(0,1),(1,-1),(1,0),(1,1)]
        for _ in range(COUNTRY_DILATE):
            empty = grid == 0
            if not empty.any():
                break
            fill = np.zeros_like(grid)
            for dr, dc in neighbors:
                shifted = np.roll(np.roll(grid, dr, axis=0), dc, axis=1)
                mask = empty & (shifted != 0) & (fill == 0)
                fill[mask] = shifted[mask]
            grid[fill != 0] = fill[fill != 0]

        self.country_grid = grid

    def _build_adjacency(self):
        self.adjacency = {n: set() for n in self.country_names[1:]}
        g = self.country_grid
        for dr, dc in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            shifted = np.roll(np.roll(g, dr, axis=0), dc, axis=1)
            mask = (g != 0) & (shifted != 0) & (g != shifted)
            rows, cols = np.where(mask)
            for r, c in zip(rows, cols):
                a = self.country_names[int(g[r, c])]
                b = self.country_names[int(shifted[r, c])]
                self.adjacency[a].add(b)
                self.adjacency[b].add(a)

    def _init_game_state(self):
        self.phase           = 'pick'
        self.owner           = {n: 0 for n in self.country_names[1:]}
        self.attacks         = {}
        self.selected        = None
        self.phase_timer     = 0.0
        self.mouse_press_pos = None

    def _setup_game_ui(self):
        self.phase_label = OnscreenText(
            text='Click any country to claim your starting territory',
            pos=(0, 0.88), scale=0.055,
            fg=(1, 1, 1, 1), shadow=(0, 0, 0, 0.8),
            align=TextNode.ACenter, mayChange=True,
        )
        self.timer_label = OnscreenText(
            text='', pos=(0, 0.78), scale=0.07,
            fg=(1, 1, 0.2, 1), shadow=(0, 0, 0, 0.8),
            align=TextNode.ACenter, mayChange=True,
        )

    def _setup_grid_lines(self):
        ls = LineSegs()
        ls.setColor(0.25, 0.30, 0.40, 0.55)
        ls.setThickness(1.0)
        r = MESH_RADIUS * 1.001
        for lon_deg in range(0, 360, 30):
            lon = math.radians(lon_deg)
            first = True
            for lat_step in range(-90, 91, 2):
                lat = math.radians(lat_step)
                x = r * math.cos(lat) * math.sin(lon)
                y = -r * math.cos(lat) * math.cos(lon)
                z = r * math.sin(lat)
                if first:
                    ls.moveTo(x, y, z); first = False
                else:
                    ls.drawTo(x, y, z)
        for lat_deg in range(-60, 90, 30):
            lat = math.radians(lat_deg)
            first = True
            for lon_step in range(0, 361, 2):
                lon = math.radians(lon_step)
                x = r * math.cos(lat) * math.sin(lon)
                y = -r * math.cos(lat) * math.cos(lon)
                z = r * math.sin(lat)
                if first:
                    ls.moveTo(x, y, z); first = False
                else:
                    ls.drawTo(x, y, z)
        self.globe_root.attachNewNode(ls.create()).setLightOff()

    def _setup_mouse(self):
        self.accept('mouse1',    self._on_drag_start)
        self.accept('mouse1-up', self._on_drag_stop)

    def _setup_hover_ui(self):
        self.hover_text = OnscreenText(
            text='', pos=(0, -0.92), scale=0.055,
            fg=(1, 1, 1, 1), shadow=(0, 0, 0, 0.8),
            align=TextNode.ACenter, mayChange=True,
        )

    # ------------------------------------------------------------------
    # Mouse drag
    # ------------------------------------------------------------------

    def _on_drag_start(self):
        if self.mouseWatcherNode.hasMouse():
            m = self.mouseWatcherNode.getMouse()
            self.last_mouse      = LVector2f(m.x, m.y)
            self.mouse_press_pos = LVector2f(m.x, m.y)
            self.drag_anchor     = self._screen_to_sphere(m.x, m.y)
            self.dragging        = True

    def _on_drag_stop(self):
        self.dragging = False
        if self.mouse_press_pos and self.mouseWatcherNode.hasMouse():
            m = self.mouseWatcherNode.getMouse()
            if (LVector2f(m.x, m.y) - self.mouse_press_pos).length() < 0.02:
                self._on_click(m.x, m.y)

    def _screen_to_sphere(self, mx, my):
        """Ray–sphere intersection; returns world-space unit vector of hit, or None."""
        near, far = Point3(), Point3()
        self.camLens.extrude(LVector2f(mx, my), near, far)
        o = self.render.getRelativePoint(self.camera, near)
        d = (self.render.getRelativePoint(self.camera, far) - o).normalized()
        b    = 2 * o.dot(d)
        c    = o.dot(o) - GLOBE_RADIUS**2
        disc = b*b - 4*c
        if disc < 0:
            return None
        t = (-b - math.sqrt(disc)) / 2
        if t < 0:
            return None
        return LVector3f(o + d * t).normalized()

    def _on_drag_move(self):
        if not self.mouseWatcherNode.hasMouse() or self.drag_anchor is None:
            return
        m = self.mouseWatcherNode.getMouse()
        cur = LVector2f(m.x, m.y)
        if (cur - self.last_mouse).length() < 1e-6:
            return
        self.last_mouse = cur

        new_anchor = self._screen_to_sphere(cur.x, cur.y)
        if new_anchor is None:
            return

        # Rotate globe so the grabbed world-space point lands where the cursor is.
        axis = self.drag_anchor.cross(new_anchor)
        if axis.length() < 1e-8:
            return
        axis.normalize()
        angle = math.acos(max(-1.0, min(1.0, self.drag_anchor.dot(new_anchor))))
        q_inc = LQuaternionf()
        q_inc.setFromAxisAngleRad(angle, axis)
        self.globe_quat  = q_inc * self.globe_quat
        self.drag_anchor = new_anchor   # anchor is now at cursor; continue from here
        self.globe_root.setQuat(self.globe_quat)

    # ------------------------------------------------------------------
    # Click dispatch & gameplay
    # ------------------------------------------------------------------

    def _on_click(self, mx, my):
        hit = self._screen_to_sphere(mx, my)
        if hit is None:
            return
        q_inv = LQuaternionf(self.globe_quat); q_inv.invertInPlace()
        sn  = q_inv.xform(hit)
        lat = math.asin(max(-1.0, min(1.0, sn.z)))
        lon = math.atan2(sn.x, -sn.y)
        row = max(0, min(COUNTRY_ROWS-1, int((lat + math.pi/2) / math.pi * COUNTRY_ROWS)))
        col = int((lon + math.pi) / (2*math.pi) * COUNTRY_COLS) % COUNTRY_COLS
        idx = int(self.country_grid[row, col])
        if idx == 0:
            return
        name = self.country_names[idx]
        if self.phase == 'pick':
            self._handle_pick(name)
        elif self.phase == 'deploy':
            self._handle_deploy(name)

    def _handle_pick(self, name):
        self.owner[name] = 1
        self._set_country_color(name, 1)
        remaining = [n for n, o in self.owner.items() if o == 0]
        random.shuffle(remaining)
        for ai_id in range(2, 2 + NUM_AI):
            if remaining:
                picked = remaining.pop()
                self.owner[picked] = ai_id
                self._set_country_color(picked, ai_id)
        self._enter_deploy()

    def _handle_deploy(self, name):
        o = self.owner.get(name, 0)
        if o == 1:
            if self.selected and self.selected != name:
                self._set_country_color(self.selected, 1)
            self.selected = name
            self._apply_color(name, SELECTED_COLOR)
        elif self.selected and name in self.adjacency.get(self.selected, set()):
            if self.attacks.get(self.selected) == name:
                del self.attacks[self.selected]
                self._set_country_color(name, self.owner[name])
            else:
                prev = self.attacks.get(self.selected)
                if prev:
                    self._set_country_color(prev, self.owner[prev])
                self.attacks[self.selected] = name
                self._apply_color(name, TARGETED_COLOR)

    def _set_country_color(self, name, owner_id):
        self.country_nps[name].setColor(*OWNER_COLORS[owner_id])

    def _apply_color(self, name, rgba):
        self.country_nps[name].setColor(*rgba)

    def _enter_deploy(self):
        self.phase       = 'deploy'
        self.attacks     = {}
        self.selected    = None
        self.phase_timer = DEPLOY_DURATION
        self.phase_label.setText('Deploy — select your country, then click a neighbor to attack')

    def _enter_fight(self):
        self.phase       = 'fight'
        self.phase_timer = FIGHT_DURATION

        for ai_id in range(2, 2 + NUM_AI):
            owned = [n for n, o in self.owner.items() if o == ai_id]
            for country in owned:
                targets = [n for n in self.adjacency.get(country, set())
                           if self.owner[n] != ai_id]
                if targets:
                    self.attacks[country] = random.choice(targets)

        results = {}
        for attacker, target in self.attacks.items():
            atk = self.country_data.get(attacker, {}).get('power', 1.0)
            dfn = self.country_data.get(target,   {}).get('power', 1.0)
            if random.random() < atk / (atk + dfn):
                results[target] = self.owner[attacker]

        for target, new_owner in results.items():
            self.owner[target] = new_owner
            self._set_country_color(target, new_owner)

        if self.selected:
            self._set_country_color(self.selected, 1)
            self.selected = None

        self.phase_label.setText('Fight!')
        self._check_win_condition()

    def _check_win_condition(self):
        player_owns = sum(1 for o in self.owner.values() if o == 1)
        if player_owns == 0:
            self.phase_label.setText('Defeated!  Press Escape to quit.')
            self.phase = 'over'
        elif all(o == 1 for o in self.owner.values()):
            self.phase_label.setText('Victory!  You control the world.')
            self.phase = 'over'

    # ------------------------------------------------------------------
    # Hover detection
    # ------------------------------------------------------------------

    def _get_hover_country(self):
        if not self.mouseWatcherNode.hasMouse():
            return ''
        mp  = self.mouseWatcherNode.getMouse()
        hit = self._screen_to_sphere(mp.x, mp.y)
        if hit is None:
            return ''

        q_inv = LQuaternionf(self.globe_quat)
        q_inv.invertInPlace()
        sn  = q_inv.xform(hit)   # globe-local unit direction
        lat = math.asin(max(-1.0, min(1.0, sn.z)))
        lon = math.atan2(sn.x, -sn.y)
        row = max(0, min(COUNTRY_ROWS-1,
                  int((lat + math.pi/2) / math.pi * COUNTRY_ROWS)))
        col = int((lon + math.pi) / (2*math.pi) * COUNTRY_COLS) % COUNTRY_COLS
        idx = int(self.country_grid[row, col])
        return self.country_names[idx] if idx else ''

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    def _update(self, task):
        dt = globalClock.getDt()

        if self.dragging:
            self._on_drag_move()

        if self.phase == 'deploy':
            self.phase_timer -= dt
            self.timer_label.setText(f'{max(0, self.phase_timer):.0f}s')
            if self.phase_timer <= 0:
                self._enter_fight()
        elif self.phase == 'fight':
            self.phase_timer -= dt
            self.timer_label.setText('')
            if self.phase_timer <= 0:
                self._enter_deploy()
        else:
            self.timer_label.setText('')

        day_angle = (globalClock.getFrameTime() % DAY_DURATION) / DAY_DURATION * 360
        self.sun_np.setHpr(day_angle, -35, 0)

        name = self._get_hover_country()
        if name and name in self.country_data:
            power = self.country_data[name]['power']
            self.hover_text.setText(f'{name}  •  Power: {power:.1f}')
        else:
            self.hover_text.setText(name)
        return Task.cont


if __name__ == '__main__':
    EarthGame().run()

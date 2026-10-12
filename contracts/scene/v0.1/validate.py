#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Проверка файла jinr-mc-scene v0.1.

Запуск из терминала:
    python validate.py scene.json [ещё.json ...] [--strict] [--verbose]

    --strict   предупреждения считаются ошибками (так гонять перед отправкой файла)
    --verbose  показывать ещё и справочные сообщения INFO

Запуск из FreeCAD (консоль Python или макрос):
    import sys; sys.path.append("/путь/к/jinr-mc-scene-v0.1")
    import validate
    issues = validate.validate_file("/путь/scene.json")
    validate.print_issues(issues)

Нужен только стандартный Python 3.8+, сторонние пакеты не требуются.
Код возврата: 0 - ошибок нет, 1 - есть ошибки, 2 - не удалось прочитать файл.
"""
from __future__ import print_function

import hashlib
import json
import math
import os
import random
import re
import struct
import sys

READER_VERSION = (0, 1)
KNOWN_EXTENSIONS = {"JINR_target_hints"}
TOL = 1e-3  # мм: допуск касания в геометрических проверках
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SCHEMA = os.path.join(HERE, "schema", "scene.schema.json")


# --------------------------------------------------------------------------
# Сообщения
# --------------------------------------------------------------------------
class Issue(object):
    __slots__ = ("level", "code", "where", "msg")

    def __init__(self, level, code, where, msg):
        self.level, self.code, self.where, self.msg = level, code, where, msg

    def __repr__(self):
        return "%s %s %s: %s" % (self.level, self.code, self.where, self.msg)


class Report(object):
    def __init__(self, strict):
        self.strict = strict
        self.items = []

    def error(self, code, where, msg):
        self.items.append(Issue("ERROR", code, where, msg))

    def warn(self, code, where, msg):
        self.items.append(Issue("ERROR" if self.strict else "WARN", code, where, msg))

    def info(self, code, where, msg):
        self.items.append(Issue("INFO", code, where, msg))

    def has_errors(self):
        return any(i.level == "ERROR" for i in self.items)


# --------------------------------------------------------------------------
# Мини-валидатор JSON Schema (то подмножество, что используется в scene.schema.json)
# --------------------------------------------------------------------------
_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: (isinstance(v, int) and not isinstance(v, bool))
    or (isinstance(v, float) and v.is_integer()),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _jtype(v):
    for name in ("null", "boolean", "integer", "number", "string", "array", "object"):
        if _TYPES[name](v):
            return name
    return type(v).__name__


class SchemaChecker(object):
    def __init__(self, schema):
        self.root = schema

    def resolve(self, s):
        while "$ref" in s:
            ref = s["$ref"]
            if not ref.startswith("#/"):
                raise ValueError("внешние $ref не поддерживаются: " + ref)
            node = self.root
            for part in ref[2:].split("/"):
                node = node[part]
            s = node
        return s

    def check(self, inst):
        out = []  # (kind, path, msg); kind: "error" | "unknown"
        self._check(inst, self.root, "", out)
        return out

    def _check(self, inst, s, path, out):
        s = self.resolve(s)
        p = path or "/"
        if "const" in s and inst != s["const"]:
            out.append(("error", p, "ожидалось %r, получено %r" % (s["const"], inst)))
            return
        if "enum" in s and inst not in s["enum"]:
            out.append(("error", p, "значение %r не из списка %r" % (inst, s["enum"])))
            return
        if "type" in s:
            types = s["type"] if isinstance(s["type"], list) else [s["type"]]
            if not any(_TYPES[t](inst) for t in types):
                out.append(("error", p, "ожидался тип %s, получен %s" % ("/".join(types), _jtype(inst))))
                return
        if isinstance(inst, str):
            if "pattern" in s and not re.search(s["pattern"], inst):
                out.append(("error", p, "строка %r не подходит под шаблон %s" % (inst, s["pattern"])))
            if "maxLength" in s and len(inst) > s["maxLength"]:
                out.append(("error", p, "строка длиннее %d символов" % s["maxLength"]))
        if _TYPES["number"](inst):
            if "minimum" in s and inst < s["minimum"]:
                out.append(("error", p, "%r меньше минимума %r" % (inst, s["minimum"])))
            if "exclusiveMinimum" in s and inst <= s["exclusiveMinimum"]:
                out.append(("error", p, "%r должно быть больше %r" % (inst, s["exclusiveMinimum"])))
            if "maximum" in s and inst > s["maximum"]:
                out.append(("error", p, "%r больше максимума %r" % (inst, s["maximum"])))
        if isinstance(inst, list):
            if "minItems" in s and len(inst) < s["minItems"]:
                out.append(("error", p, "нужно не меньше %d элементов, есть %d" % (s["minItems"], len(inst))))
            if "maxItems" in s and len(inst) > s["maxItems"]:
                out.append(("error", p, "нужно не больше %d элементов, есть %d" % (s["maxItems"], len(inst))))
            if s.get("uniqueItems"):
                seen = []
                for v in inst:
                    if v in seen:
                        out.append(("error", p, "повторяющийся элемент %r" % (v,)))
                    seen.append(v)
            if "items" in s:
                for i, v in enumerate(inst):
                    self._check(v, s["items"], "%s/%d" % (path, i), out)
        if isinstance(inst, dict):
            for k in s.get("required", []):
                if k not in inst:
                    out.append(("error", p, "нет обязательного поля %r" % k))
            props = s.get("properties", {})
            addl = s.get("additionalProperties", True)
            for k, v in inst.items():
                if "propertyNames" in s:
                    sub = []
                    self._check(k, s["propertyNames"], "%s/%s" % (path, k), sub)
                    out.extend(sub)
                if k in props:
                    self._check(v, props[k], "%s/%s" % (path, k), out)
                elif addl is False:
                    out.append(("unknown", "%s/%s" % (path, k), "неизвестное поле %r" % k))
                elif isinstance(addl, dict):
                    self._check(v, addl, "%s/%s" % (path, k), out)
        if "oneOf" in s:
            self._one_of(inst, s["oneOf"], path, out)
        if "anyOf" in s:
            self._any_of(inst, s["anyOf"], path, out)

    def _discriminator(self, inst, branches):
        if not isinstance(inst, dict):
            return None
        rb = [self.resolve(b) for b in branches]
        for key in ("type", "convention"):
            consts = [b.get("properties", {}).get(key, {}).get("const") for b in rb]
            if all(c is not None for c in consts):
                return key, consts, rb
        return None

    def _one_of(self, inst, branches, path, out):
        d = self._discriminator(inst, branches)
        p = path or "/"
        if d:
            key, consts, rb = d
            if key not in inst:
                out.append(("error", p, "нет поля %r (одно из: %s)" % (key, ", ".join(consts))))
                return
            if inst[key] not in consts:
                out.append(("error", p + "/" + key,
                            "%s = %r здесь недопустимо; допустимо: %s" % (key, inst[key], ", ".join(consts))))
                return
            self._check(inst, rb[consts.index(inst[key])], path, out)
            return
        results = []
        for b in branches:
            sub = []
            self._check(inst, b, path, sub)
            results.append([x for x in sub if x[0] == "error"])
        ok = [r for r in results if not r]
        if len(ok) == 1:
            return
        if not ok:
            best = min(results, key=len)
            out.append(("error", p, "не подходит ни под один вариант: " + best[0][2]))
        else:
            out.append(("error", p, "подходит под несколько вариантов сразу"))

    def _any_of(self, inst, branches, path, out):
        for b in branches:
            sub = []
            self._check(inst, b, path, sub)
            if not [x for x in sub if x[0] == "error"]:
                return
        rb = [self.resolve(b) for b in branches]
        if all(set(b.keys()) == {"required"} for b in rb):
            alts = " или ".join("[" + ", ".join(b["required"]) + "]" for b in rb)
            out.append(("error", path or "/", "нужно одно из: " + alts))
        else:
            out.append(("error", path or "/", "не подходит ни под один вариант anyOf"))


# --------------------------------------------------------------------------
# Линейная алгебра
# --------------------------------------------------------------------------
def mat_vec(m, v):
    return [m[0][0] * v[0] + m[0][1] * v[1] + m[0][2] * v[2],
            m[1][0] * v[0] + m[1][1] * v[1] + m[1][2] * v[2],
            m[2][0] * v[0] + m[2][1] * v[1] + m[2][2] * v[2]]


def transpose(m):
    return [[m[j][i] for j in range(3)] for i in range(3)]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def det3(m):
    return (m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1])
            - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0])
            + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]))


IDENTITY = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def rotation_matrix(rot):
    conv = rot["convention"]
    if conv == "identity":
        return [row[:] for row in IDENTITY]
    if conv == "matrix_active":
        return [[float(x) for x in row] for row in rot["matrix"]]
    if conv == "euler_xyz_extrinsic_deg":
        a, b, c = [math.radians(x) for x in rot["angles"]]
        rx = [[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]]
        ry = [[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]]
        rz = [[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]]
        return mat_mul(rz, mat_mul(ry, rx))
    raise ValueError(conv)


def rotation_problem(m):
    """None, если m - правильный поворот; иначе текст проблемы."""
    mmt = mat_mul(m, transpose(m))
    dev = max(abs(mmt[i][j] - (1.0 if i == j else 0.0)) for i in range(3) for j in range(3))
    if dev > 1e-6:
        return "матрица не ортонормирована (отклонение M*Mт от единичной %.2e)" % dev
    if det3(m) < 0:
        return "det = -1: это отражение, а не поворот"
    return None


class Transform(object):
    def __init__(self, tf):
        if tf is None:
            self.r, self.t = IDENTITY, [0.0, 0.0, 0.0]
        else:
            self.r = rotation_matrix(tf["rotation"])
            self.t = [float(x) for x in tf["translation"]]
        self.rt = transpose(self.r)

    def apply(self, p):
        q = mat_vec(self.r, p)
        return [q[0] + self.t[0], q[1] + self.t[1], q[2] + self.t[2]]

    def inverse_apply(self, p):
        return mat_vec(self.rt, [p[0] - self.t[0], p[1] - self.t[1], p[2] - self.t[2]])


# --------------------------------------------------------------------------
# Геометрия фигур (в локальной системе фигуры)
# --------------------------------------------------------------------------
def _lin(a, b, n):
    return [a + (b - a) * i / (n - 1) for i in range(n)]


def _ring(r, z, n=48):
    return [[r * math.cos(2 * math.pi * k / n), r * math.sin(2 * math.pi * k / n), z] for k in range(n)]


class ShapeGeom(object):
    """Обёртка над словарём shape. Для меша нужен загруженный STL (mesh)."""

    def __init__(self, d, mesh=None):
        self.d = d
        self.type = d["type"]
        self.own_tf = Transform(d["transform"]) if "transform" in d else None
        self.mesh = mesh
        if self.type == "boolean":
            self.left = ShapeGeom(d["left"])
            self.right = ShapeGeom(d["right"])

    # --- принадлежность точки (tol > 0 раздувает фигуру, tol < 0 сжимает)
    def inside_tf(self, p, tol):
        if self.own_tf is not None:
            p = self.own_tf.inverse_apply(p)
        return self.inside(p, tol)

    def inside(self, p, tol):
        d, t = self.d, self.type
        x, y, z = p
        if t == "box":
            hx, hy, hz = [s / 2.0 for s in d["size"]]
            return abs(x) <= hx + tol and abs(y) <= hy + tol and abs(z) <= hz + tol
        if t == "cylinder":
            rho = math.hypot(x, y)
            ri = d.get("inner_radius", 0) or 0
            if abs(z) > d["height"] / 2.0 + tol or rho > d["radius"] + tol:
                return False
            return not (ri > 0 and rho < ri - tol)
        if t == "cone":
            h = d["height"]
            if abs(z) > h / 2.0 + tol:
                return False
            f = min(max((z + h / 2.0) / h, 0.0), 1.0)
            ro = d["radius_bottom"] + (d["radius_top"] - d["radius_bottom"]) * f
            rib, rit = d.get("inner_radius_bottom", 0) or 0, d.get("inner_radius_top", 0) or 0
            ri = rib + (rit - rib) * f
            rho = math.hypot(x, y)
            if rho > ro + tol:
                return False
            return not ((rib > 0 or rit > 0) and rho < ri - tol)
        if t == "sphere":
            r = math.sqrt(x * x + y * y + z * z)
            ri = d.get("inner_radius", 0) or 0
            return r <= d["radius"] + tol and not (ri > 0 and r < ri - tol)
        if t == "torus":
            q = math.hypot(math.hypot(x, y) - d["major_radius"], z)
            return q <= d["minor_radius"] + tol
        if t == "boolean":
            op = d["op"]
            a = self.left.inside_tf(p, tol)
            if op == "union":
                return a or self.right.inside_tf(p, tol)
            if op == "intersect":
                return a and self.right.inside_tf(p, tol)
            return a and not self.right.inside_tf(p, -tol)
        if t == "mesh" and self.mesh is not None:
            return self.mesh.inside(p, tol)
        return None

    # --- точки, гарантированно принадлежащие фигуре (на её поверхности)
    def samples_tf(self):
        pts = self.samples()
        if self.own_tf is not None:
            pts = [self.own_tf.apply(p) for p in pts]
        return pts

    def samples(self):
        d, t = self.d, self.type
        pts = []
        if t == "box":
            h = [s / 2.0 for s in d["size"]]
            g = _lin(-1.0, 1.0, 7)
            for ax in range(3):
                a1, a2 = [i for i in range(3) if i != ax]
                for sgn in (-1.0, 1.0):
                    for u in g:
                        for v in g:
                            p = [0.0, 0.0, 0.0]
                            p[ax] = sgn * h[ax]
                            p[a1] = u * h[a1]
                            p[a2] = v * h[a2]
                            pts.append(p)
        elif t in ("cylinder", "cone"):
            h = d["height"]
            if t == "cylinder":
                rb = rt = d["radius"]
                ib = it = d.get("inner_radius", 0) or 0
            else:
                rb, rt = d["radius_bottom"], d["radius_top"]
                ib, it = d.get("inner_radius_bottom", 0) or 0, d.get("inner_radius_top", 0) or 0
            for f in _lin(0.0, 1.0, 7):
                z = -h / 2.0 + h * f
                pts += _ring(rb + (rt - rb) * f, z)
                if ib > 0 or it > 0:
                    pts += _ring(ib + (it - ib) * f, z)
            for z, ro, ri in ((-h / 2.0, rb, ib), (h / 2.0, rt, it)):
                for r in _lin(ri, ro, 4):
                    pts += _ring(r, z) if r > 0 else [[0.0, 0.0, z]]
        elif t == "sphere":
            for r in [d["radius"]] + ([d["inner_radius"]] if d.get("inner_radius") else []):
                for i in range(13):
                    th = math.pi * i / 12
                    for k in range(24):
                        ph = 2 * math.pi * k / 24
                        pts.append([r * math.sin(th) * math.cos(ph), r * math.sin(th) * math.sin(ph), r * math.cos(th)])
        elif t == "torus":
            R, r = d["major_radius"], d["minor_radius"]
            for i in range(36):
                u = 2 * math.pi * i / 36
                for k in range(18):
                    v = 2 * math.pi * k / 18
                    pts.append([(R + r * math.cos(v)) * math.cos(u), (R + r * math.cos(v)) * math.sin(u), r * math.sin(v)])
        elif t == "boolean":
            cand = self.left.samples_tf() + self.right.samples_tf()
            pts = [p for p in cand if self.inside(p, TOL)]
        elif t == "mesh":
            pts = list(self.mesh.vertices) if self.mesh is not None else []
        return pts

    # --- аналитический объём (None, если не считается напрямую)
    def volume(self):
        d, t = self.d, self.type
        if t == "box":
            return d["size"][0] * d["size"][1] * d["size"][2]
        if t == "cylinder":
            ri = d.get("inner_radius", 0) or 0
            return math.pi * (d["radius"] ** 2 - ri ** 2) * d["height"]
        if t == "cone":
            def fr(a, b):
                return math.pi * d["height"] / 3.0 * (a * a + a * b + b * b)
            return fr(d["radius_bottom"], d["radius_top"]) - fr(d.get("inner_radius_bottom", 0) or 0,
                                                                  d.get("inner_radius_top", 0) or 0)
        if t == "sphere":
            ri = d.get("inner_radius", 0) or 0
            return 4.0 / 3.0 * math.pi * (d["radius"] ** 3 - ri ** 3)
        if t == "torus":
            return 2 * math.pi ** 2 * d["major_radius"] * d["minor_radius"] ** 2
        return None


def _extent(pts):
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    return lo, hi


def mc_volume(geom, n=60000, seed=12345):
    """Оценка объёма булевой фигуры методом Монте-Карло: (V, sigma)."""
    pts = []
    _collect_leaf_points(geom, pts)
    lo, hi = _extent(pts)
    pad = [0.01 * (hi[i] - lo[i]) + TOL for i in range(3)]
    lo = [lo[i] - pad[i] for i in range(3)]
    hi = [hi[i] + pad[i] for i in range(3)]
    box_v = (hi[0] - lo[0]) * (hi[1] - lo[1]) * (hi[2] - lo[2])
    rnd = random.Random(seed)
    hit = 0
    for _ in range(n):
        p = [rnd.uniform(lo[0], hi[0]), rnd.uniform(lo[1], hi[1]), rnd.uniform(lo[2], hi[2])]
        if geom.inside(p, 0.0):
            hit += 1
    f = hit / float(n)
    sigma = box_v * math.sqrt(max(f * (1 - f), 1e-12) / n)
    return box_v * f, sigma


def _collect_leaf_points(geom, out):
    """Все точки поверхностей листьев булева дерева в системе этого дерева."""
    if geom.type == "boolean":
        for child in (geom.left, geom.right):
            sub = []
            _collect_leaf_points(child, sub)
            if child.own_tf is not None:
                sub = [child.own_tf.apply(p) for p in sub]
            out.extend(sub)
    else:
        out.extend(geom.samples())


# --------------------------------------------------------------------------
# STL
# --------------------------------------------------------------------------
def read_stl(data):
    """Возвращает (encoding, список треугольников [(v0,v1,v2), ...])."""
    if len(data) >= 84:
        n = struct.unpack("<I", data[80:84])[0]
        if 84 + 50 * n == len(data):
            tris = []
            for i in range(n):
                off = 84 + 50 * i + 12
                v = struct.unpack("<9f", data[off:off + 36])
                tris.append(((v[0], v[1], v[2]), (v[3], v[4], v[5]), (v[6], v[7], v[8])))
            return "stl-binary", tris
    text = data.decode("ascii", errors="replace")
    if not text.lstrip().lower().startswith("solid"):
        raise ValueError("файл не похож ни на двоичный, ни на текстовый STL")
    nums = re.findall(r"vertex\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)\s+([-+0-9.eE]+)", text)
    if len(nums) % 3:
        raise ValueError("число вершин в текстовом STL не кратно 3")
    vs = [tuple(float(c) for c in v) for v in nums]
    return "stl-ascii", [(vs[i], vs[i + 1], vs[i + 2]) for i in range(0, len(vs), 3)]


class MeshGeom(object):
    """Замкнутая сетка: принадлежность точки по чётности пересечений луча."""

    DIR = (0.8017837257372732, 0.5345224838248488, 0.2672612419124244)

    def __init__(self, tris, vertices):
        self.tris = [tuple(tuple(float(c) for c in v) for v in t) for t in tris]
        self.vertices = vertices
        self.lo, self.hi = _extent(vertices)

    def inside(self, p, tol):
        if any(p[i] < self.lo[i] - abs(tol) or p[i] > self.hi[i] + abs(tol) for i in range(3)):
            return False
        dx, dy, dz = self.DIR
        px, py, pz = p
        hits = 0
        for a, b, c in self.tris:
            e1 = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
            e2 = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
            hx, hy, hz = dy * e2[2] - dz * e2[1], dz * e2[0] - dx * e2[2], dx * e2[1] - dy * e2[0]
            det = e1[0] * hx + e1[1] * hy + e1[2] * hz
            if abs(det) < 1e-12:
                continue
            inv = 1.0 / det
            sx, sy, sz = px - a[0], py - a[1], pz - a[2]
            u = (sx * hx + sy * hy + sz * hz) * inv
            if u < 0.0 or u > 1.0:
                continue
            qx, qy, qz = sy * e1[2] - sz * e1[1], sz * e1[0] - sx * e1[2], sx * e1[1] - sy * e1[0]
            v = (dx * qx + dy * qy + dz * qz) * inv
            if v < 0.0 or u + v > 1.0:
                continue
            if (e2[0] * qx + e2[1] * qy + e2[2] * qz) * inv > 0.0:
                hits += 1
        return hits % 2 == 1


def mesh_stats(tris):
    key = lambda v: (round(v[0], 6), round(v[1], 6), round(v[2], 6))
    directed = {}
    vol = 0.0
    degenerate = 0
    for a, b, c in tris:
        ka, kb, kc = key(a), key(b), key(c)
        if ka == kb or kb == kc or kc == ka:
            degenerate += 1
            continue
        for e in ((ka, kb), (kb, kc), (kc, ka)):
            directed[e] = directed.get(e, 0) + 1
        vol += (a[0] * (b[1] * c[2] - b[2] * c[1]) - a[1] * (b[0] * c[2] - b[2] * c[0])
                + a[2] * (b[0] * c[1] - b[1] * c[0])) / 6.0
    open_edges = 0
    bad_orient = 0
    for (u, v), cnt in directed.items():
        back = directed.get((v, u), 0)
        if back == 0:
            open_edges += 1
        if cnt > 1:
            bad_orient += 1
    verts = list({key(v) for t in tris for v in t})
    return {"volume": vol, "open_edges": open_edges, "bad_orient": bad_orient,
            "degenerate": degenerate, "vertices": [list(v) for v in verts]}


# --------------------------------------------------------------------------
# Проверка документа
# --------------------------------------------------------------------------
def _parse_version(s):
    a, b = s.split(".")
    return int(a), int(b)


def _walk_extensions(node, found):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "extensions" and isinstance(v, dict):
                found.update(v.keys())
            _walk_extensions(v, found)
    elif isinstance(node, list):
        for v in node:
            _walk_extensions(v, found)


def _plural_hint(ratio):
    for r, txt in ((8.0, "в 8 раз - похоже на половинные размеры коробки вместо полных"),
                   (0.125, "в 8 раз меньше - похоже на удвоенные размеры"),
                   (2.0, "в 2 раза - похоже на половинную высоту вместо полной"),
                   (0.5, "в 2 раза меньше - похоже на удвоенную высоту"),
                   (4.0, "в 4 раза - похоже, что радиус записан как диаметр/2 или наоборот"),
                   (0.25, "в 4 раза меньше - похоже, что в radius записан диаметр")):
        if abs(ratio - r) / r < 0.01:
            return " (" + txt + ")"
    return ""


def validate_document(doc, base_dir, rep, schema):
    # 0. формат и версия - до схемы, чтобы при чужой версии не сыпать сотней ошибок
    if not isinstance(doc, dict):
        rep.error("E001", "/", "в корне должен быть объект JSON")
        return
    if doc.get("format") != "jinr-mc-scene":
        rep.error("E002", "/format", "ожидалось 'jinr-mc-scene', получено %r" % doc.get("format"))
        return
    fv = doc.get("format_version")
    try:
        ver = _parse_version(fv)
    except Exception:
        rep.error("E003", "/format_version", "версия должна быть вида '0.1', получено %r" % (fv,))
        return
    if ver != READER_VERSION:
        if ver[0] == 0 or ver[0] != READER_VERSION[0]:
            rep.error("E003", "/format_version",
                      "этот валидатор понимает только %d.%d; для %s нужен апгрейдер или новый validate.py"
                      % (READER_VERSION + (fv,)))
            return
        mrv = doc.get("min_reader_version", fv)
        if _parse_version(mrv) > READER_VERSION:
            rep.error("E003", "/min_reader_version", "файл требует читателя не ниже %s" % mrv)
            return
        rep.warn("W003", "/format_version", "файл новее валидатора (%s), неизвестные поля будут пропущены" % fv)

    # 1. структура по схеме
    for kind, path, msg in SchemaChecker(schema).check(doc):
        if kind == "unknown":
            rep.warn("W100", path, msg + " - его никто не прочитает (опечатка? новое поле - через версию схемы или extras)")
        else:
            rep.error("E100", path, msg)
    if rep.has_errors():
        rep.info("I000", "/", "дальнейшие проверки пропущены, пока не исправлена структура")
        return

    # 2. ссылки и идентификаторы
    ids = {}
    for kind in ("materials", "bodies"):
        for i, obj in enumerate(doc[kind]):
            where = "/%s/%d" % (kind, i)
            if obj["id"] in ids:
                rep.error("E201", where, "id %r уже занят (%s)" % (obj["id"], ids[obj["id"]]))
            else:
                ids[obj["id"]] = where
    mats = {m["id"]: m for m in doc["materials"]}
    bodies = {b["id"]: b for b in doc["bodies"]}
    if doc["world"]["material"] not in mats:
        rep.error("E204", "/world/material", "материал %r не описан в materials" % doc["world"]["material"])
    used_mats = set()
    for b in doc["bodies"]:
        w = "bodies/" + b["id"]
        if b["material"] not in mats:
            rep.error("E202", w + "/material", "материал %r не описан в materials" % b["material"])
        used_mats.add(b["material"])
        if b["parent"] is not None and b["parent"] not in bodies:
            rep.error("E203", w + "/parent", "родитель %r не найден среди bodies" % b["parent"])
        if b["parent"] == b["id"]:
            rep.error("E203", w + "/parent", "тело не может быть родителем самому себе")
    for b in doc["bodies"]:  # циклы
        seen, cur = set(), b
        while cur is not None and cur["parent"] is not None and cur["parent"] in bodies:
            if cur["id"] in seen:
                rep.error("E203", "bodies/" + b["id"], "цикл в цепочке parent")
                break
            seen.add(cur["id"])
            cur = bodies[cur["parent"]]
    used_mats.add(doc["world"]["material"])
    for m in doc["materials"]:
        w = "materials/" + m["id"]
        if m["id"] not in used_mats:
            rep.info("I201", w, "материал нигде не используется")
        comp = m.get("composition")
        if comp:
            s = sum(c["fraction"] for c in comp["components"])
            if abs(s - 1.0) > 1e-3:
                rep.error("E206", w + "/composition", "сумма долей = %.4f, должна быть 1" % s)
            els = [c["element"] for c in comp["components"]]
            if len(set(els)) != len(els):
                rep.error("E206", w + "/composition", "элемент указан дважды")
        elif "nist" in m:
            rep.info("I202", w, "только NIST-имя: для Geant4 хватит, для FLUKA/MCNP генератор возьмёт состав из базы NIST")
        hints = m.get("extensions", {}).get("JINR_target_hints", {})
        fl = hints.get("fluka", {}) if isinstance(hints, dict) else {}
        if isinstance(fl, dict) and len(str(fl.get("name", ""))) > 8:
            rep.warn("W204", w, "имя материала FLUKA длиннее 8 символов")

    # 3. расширения
    found = set()
    _walk_extensions(doc, found)
    used = set(doc.get("extensions_used", []))
    for e in sorted(found - used):
        rep.warn("W205", "/extensions_used", "расширение %s используется, но не перечислено" % e)
    for e in doc.get("extensions_required", []):
        if e not in used:
            rep.error("E205", "/extensions_required", "%s нет в extensions_used" % e)
        if e not in KNOWN_EXTENSIONS:
            rep.error("E205", "/extensions_required", "обязательное расширение %s неизвестно этому читателю" % e)

    if rep.has_errors():
        rep.info("I000", "/", "геометрические проверки пропущены, пока есть ошибки ссылок")
        return

    # 4. геометрия каждого тела
    geoms, tfs = {}, {}
    for b in doc["bodies"]:
        w = "bodies/" + b["id"]
        sh = b["shape"]
        ok = True
        for path, tfd in _iter_transforms(b):
            prob = rotation_problem(rotation_matrix(tfd["rotation"]))
            if prob:
                rep.error("E210", w + path, prob)
                ok = False
        if "transform" in sh:
            rep.error("E211", w + "/shape/transform",
                      "у формы тела transform не задаётся - положение тела пишется в body.transform")
            ok = False
        for path, s in _iter_shapes(sh, "/shape"):
            ok &= _check_shape_params(s, w + path, rep)
        if not ok:
            continue
        mesh = None
        if sh["type"] == "mesh":
            mesh = _check_mesh(sh, b, base_dir, w, rep)
            if mesh is None:
                continue
        geoms[b["id"]] = ShapeGeom(sh, mesh)
        tfs[b["id"]] = Transform(b["transform"])
        _check_volume(b, geoms[b["id"]], w, rep)
        _check_bbox(b, geoms[b["id"]], tfs[b["id"]], w, rep)

    # 5. вложенность и пересечения соседей
    pts_cache = {}

    def pts_in_parent(bid):
        if bid not in pts_cache:
            pts_cache[bid] = [tfs[bid].apply(p) for p in geoms[bid].samples()]
        return pts_cache[bid]

    for b in doc["bodies"]:
        bid, pid = b["id"], b["parent"]
        if pid is None or bid not in geoms or pid not in geoms:
            continue
        parent = geoms[pid]
        bad = [p for p in pts_in_parent(bid) if not parent.inside(p, TOL)]
        if bad:
            worst = max(bad, key=lambda p: math.sqrt(p[0] ** 2 + p[1] ** 2 + p[2] ** 2))
            rep.error("E250", "bodies/" + bid,
                      "тело вылезает за родителя %r: %d контрольных точек снаружи, например (%s) в системе родителя. "
                      "Частая причина - точка привязки FreeCAD (угол коробки, основание цилиндра) вместо центра"
                      % (pid, len(bad), ", ".join("%.3f" % c for c in worst)))

    groups = {}
    for b in doc["bodies"]:
        if b["id"] in geoms:
            groups.setdefault(b["parent"], []).append(b["id"])
    for pid, members in groups.items():
        ext = {m: _extent(pts_in_parent(m)) for m in members if pts_in_parent(m)}
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, c = members[i], members[j]
                if a not in ext or c not in ext:
                    continue
                (alo, ahi), (clo, chi) = ext[a], ext[c]
                if any(ahi[k] < clo[k] - TOL or chi[k] < alo[k] - TOL for k in range(3)):
                    continue
                ga, gc = geoms[a], geoms[c]
                n_bad = sum(1 for p in pts_in_parent(a) if gc.inside(tfs[c].inverse_apply(p), -TOL))
                n_bad += sum(1 for p in pts_in_parent(c) if ga.inside(tfs[a].inverse_apply(p), -TOL))
                if n_bad:
                    rep.error("E251", "bodies/%s + %s" % (a, c),
                              "соседи (общий родитель %s) пересекаются: %d контрольных точек одного внутри другого"
                              % (pid or "мир", n_bad))


def _iter_transforms(body):
    yield "/transform", body["transform"]

    def rec(s, path):
        if "transform" in s:
            yield path + "/transform", s["transform"]
        if s["type"] == "boolean":
            for side in ("left", "right"):
                for x in rec(s[side], path + "/" + side):
                    yield x

    for x in rec(body["shape"], "/shape"):
        yield x


def _iter_shapes(s, path):
    yield path, s
    if s["type"] == "boolean":
        for side in ("left", "right"):
            for x in _iter_shapes(s[side], path + "/" + side):
                yield x


def _check_shape_params(s, where, rep):
    t = s["type"]
    if t == "cylinder" and (s.get("inner_radius") or 0) >= s["radius"]:
        rep.error("E212", where, "inner_radius >= radius")
        return False
    if t == "sphere" and (s.get("inner_radius") or 0) >= s["radius"]:
        rep.error("E212", where, "inner_radius >= radius")
        return False
    if t == "torus" and s["minor_radius"] >= s["major_radius"]:
        rep.error("E212", where, "minor_radius >= major_radius (самопересекающийся тор)")
        return False
    if t == "cone":
        if s["radius_bottom"] == 0 and s["radius_top"] == 0:
            rep.error("E212", where, "у конуса оба радиуса равны 0")
            return False
        ib, it = s.get("inner_radius_bottom") or 0, s.get("inner_radius_top") or 0
        if (ib > 0 and ib >= s["radius_bottom"]) or (it > 0 and it >= s["radius_top"]):
            rep.error("E212", where, "внутренний радиус конуса >= внешнего")
            return False
    return True


def _check_volume(b, g, w, rep):
    cad = b["verification"]["cad_volume"]
    v = g.volume()
    if v is not None:
        rel = abs(v - cad) / cad
        if rel > 1e-3:
            rep.error("E220", w + "/verification/cad_volume",
                      "объём по размерам %.6g мм3, а cad_volume = %.6g (расхождение %.2f%%)%s"
                      % (v, cad, 100 * rel, _plural_hint(cad / v)))
    elif g.type == "boolean":
        est, sig = mc_volume(g)
        if abs(est - cad) > 4 * sig + 0.002 * cad:
            rep.warn("W221", w + "/verification/cad_volume",
                     "оценка объёма булева дерева %.4g ± %.2g мм3, а cad_volume = %.4g - проверьте операнды и их transform"
                     % (est, sig, cad))


def _check_bbox(b, g, tf, w, rep):
    bb = b["verification"].get("bbox")
    if not bb:
        return
    lo, hi = bb
    if any(lo[i] > hi[i] for i in range(3)):
        rep.error("E240", w + "/verification/bbox", "min больше max")
        return
    pts = [tf.apply(p) for p in g.samples()]
    if not pts:
        return
    size = max(hi[i] - lo[i] for i in range(3))
    tol = 1e-4 * size + 0.01
    out = 0
    worst = 0.0
    for p in pts:
        d = max(max(lo[i] - p[i], p[i] - hi[i]) for i in range(3))
        if d > tol:
            out += 1
            worst = max(worst, d)
    if out:
        rep.error("E240", w + "/verification/bbox",
                  "форма с этим transform не помещается в bbox: %d точек снаружи, до %.3f мм. "
                  "Проверьте центрирование примитива и translation" % (out, worst))
        return
    elo, ehi = _extent(pts)
    gap = max(max(elo[i] - lo[i], hi[i] - ehi[i]) for i in range(3))
    if gap > 0.02 * size + 0.5:
        rep.warn("W241", w + "/verification/bbox",
                 "bbox шире формы на %.3f мм - возможно, BoundBox не оптимальный (лучше Shape.optimalBoundingBox())"
                 % gap)


def _check_mesh(sh, b, base_dir, w, rep):
    uri = sh["uri"]
    if uri.startswith("/") or ".." in uri.split("/"):
        rep.warn("W230", w + "/shape/uri", "путь лучше держать внутри папки с JSON, без '..' и абсолютных путей")
    path = os.path.join(base_dir, *uri.split("/"))
    if not os.path.isfile(path):
        rep.error("E230", w + "/shape/uri", "файл %s не найден" % uri)
        return None
    with open(path, "rb") as f:
        data = f.read()
    digest = hashlib.sha256(data).hexdigest()
    if digest != sh["sha256"]:
        rep.error("E231", w + "/shape/sha256", "sha256 не совпадает: файл изменён после экспорта (у файла %s)" % digest)
    try:
        enc, tris = read_stl(data)
    except ValueError as e:
        rep.error("E233", w + "/shape/uri", str(e))
        return None
    if enc != sh["encoding"]:
        rep.error("E233", w + "/shape/encoding", "в JSON %s, а файл на самом деле %s" % (sh["encoding"], enc))
    if len(tris) != sh["n_facets"]:
        rep.error("E232", w + "/shape/n_facets", "в JSON %d, в файле %d треугольников" % (sh["n_facets"], len(tris)))
    st = mesh_stats(tris)
    if st["degenerate"]:
        rep.warn("W237", w + "/shape", "%d вырожденных треугольников" % st["degenerate"])
    if st["open_edges"]:
        rep.error("E234", w + "/shape", "меш не замкнут: %d рёбер без пары (дыры)" % st["open_edges"])
    if st["bad_orient"]:
        rep.error("E234", w + "/shape", "ориентация треугольников несогласована (%d рёбер)" % st["bad_orient"])
    if st["volume"] < 0:
        rep.error("E235", w + "/shape", "нормали смотрят внутрь (объём сетки отрицательный)")
    cad = b["verification"]["cad_volume"]
    vol = abs(st["volume"])
    if not st["open_edges"] and cad > 0:
        rel = abs(vol - cad) / cad
        if rel > 0.10:
            rep.error("E236", w + "/verification/cad_volume",
                      "объём сетки %.6g мм3 отличается от cad_volume %.6g на %.1f%% - "
                      "не тот файл, не те единицы или STL в глобальных координатах?" % (vol, cad, 100 * rel))
        elif rel > 0.02:
            rep.warn("W236", w + "/verification/cad_volume",
                     "объём сетки отличается от cad_volume на %.1f%% - тесселяция слишком грубая?" % (100 * rel))
    if st["open_edges"] or st["bad_orient"]:
        return None  # по дырявой сетке геометрические проверки не делаем
    return MeshGeom(tris, st["vertices"])


# --------------------------------------------------------------------------
# Входные точки
# --------------------------------------------------------------------------
def load_schema(path=None):
    with open(path or DEFAULT_SCHEMA, "r", encoding="utf-8") as f:
        return json.load(f)


def validate_file(path, strict=False, schema=None):
    rep = Report(strict)
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, IOError) as e:
        rep.error("E001", path, "не удалось открыть: %s" % e)
        return rep.items
    except ValueError as e:
        rep.error("E001", path, "это не JSON: %s" % e)
        return rep.items
    validate_document(doc, os.path.dirname(os.path.abspath(path)), rep, schema or load_schema())
    return rep.items


def print_issues(issues, stream=None, verbose=False):
    stream = stream or sys.stdout
    order = {"ERROR": 0, "WARN": 1, "INFO": 2}
    for i in sorted(issues, key=lambda x: order[x.level]):
        if i.level == "INFO" and not verbose:
            continue
        stream.write("%-5s %s  %s: %s\n" % (i.level, i.code, i.where, i.msg))
    ne = sum(1 for i in issues if i.level == "ERROR")
    nw = sum(1 for i in issues if i.level == "WARN")
    stream.write("Итог: ошибок %d, предупреждений %d -> %s\n" % (ne, nw, "НЕ ПРОШЁЛ" if ne else "OK"))


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    strict = "--strict" in argv
    verbose = "--verbose" in argv
    if not args or "--help" in argv or "-h" in args:
        print(__doc__)
        return 0
    schema = load_schema()
    worst = 0
    for path in args:
        print("== %s%s" % (path, " (strict)" if strict else ""))
        issues = validate_file(path, strict, schema)
        print_issues(issues, verbose=verbose)
        if any(i.code == "E001" for i in issues):
            worst = max(worst, 2)
        elif any(i.level == "ERROR" for i in issues):
            worst = max(worst, 1)
        print()
    return worst


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

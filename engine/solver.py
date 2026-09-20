"""
solver.py -- partition a plat into KNOWN and UNKNOWN, then compute everything
derivable inside the known set, propagating to a fixpoint.

Rationale: up to now each plat was validated with hand-written checks. But
every check is really the same operation -- a constraint over several
quantities, where if all but one are known the remaining one is DETERMINED.
Formalising that turns a pile of one-off checks into an engine:

  1. Mark every quantity READ (transcribed), DERIVED (computed) or UNKNOWN.
  2. Sweep the constraint set. Any constraint with exactly one unknown
     solves it -> promote to DERIVED, recording which constraint produced it.
  3. Any constraint with zero unknowns is a CHECK -- compare and report
     residual. This is where transcription errors surface.
  4. Repeat until no further progress (fixpoint).
  5. Report the FRONTIER: the unknowns that remain, and which constraint
     each is waiting on. That is precisely the list of what to go read off
     the sheet next, or what needs a better scan.

Provenance is tracked for every value so a DERIVED number is never confused
with something actually read from the plat.
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field

READ, DERIVED, UNKNOWN = "READ", "DERIVED", "UNKNOWN"


@dataclass
class Q:
    """A scalar quantity in the plat model."""
    name: str
    value: float | None = None
    status: str = UNKNOWN
    source: str = ""
    confidence: str = ""

    @property
    def known(self):
        return self.status in (READ, DERIVED) and self.value is not None


class Model:
    def __init__(self, title=""):
        self.title = title
        self.q: dict[str, Q] = {}
        self.constraints: list[Constraint] = []
        self.checks: list[dict] = []
        self.log: list[str] = []

    def read(self, name, value, confidence="H", source="transcribed"):
        self.q[name] = Q(name, value, READ, source, confidence)
        return self.q[name]

    def unknown(self, name):
        self.q[name] = Q(name)
        return self.q[name]

    def get(self, name) -> Q:
        if name not in self.q:
            self.unknown(name)
        return self.q[name]

    def add(self, c: "Constraint"):
        c.model = self
        self.constraints.append(c)
        return c

    # ---------- propagation ----------
    def solve(self, max_passes=12, check_tol=0.35):
        for p in range(max_passes):
            progress = False
            for c in self.constraints:
                unk = [n for n in c.vars if not self.get(n).known]
                if unk:
                    # Try each unknown. A constraint may determine more than
                    # one at once (R + delta fix both arc length and chord),
                    # so gating on "exactly one unknown" silently leaves
                    # derivable quantities on the frontier. Each solve_for is
                    # defensive and returns None when its own inputs are not
                    # all known, so over-offering targets is safe.
                    for target in unk:
                        val = c.solve_for(target)
                        if val is None:
                            continue
                        qq = self.get(target)
                        qq.value = val
                        qq.status = DERIVED
                        qq.source = c.name
                        self.log.append(
                            f"pass {p+1}: DERIVED {target} = {val:.4f} via {c.name}")
                        progress = True
                if not unk:
                    r = c.residual()
                    if r is not None:
                        rec = dict(constraint=c.name, residual=r,
                                   status="ok" if abs(r) <= check_tol else "CHECK")
                        if rec not in self.checks:
                            self.checks.append(rec)
            if not progress:
                break
        return self

    def frontier(self):
        out = []
        for name, qq in self.q.items():
            if qq.known:
                continue
            waiting = []
            for c in self.constraints:
                if name in c.vars:
                    others = [n for n in c.vars if n != name and not self.get(n).known]
                    waiting.append((c.name, others))
            out.append(dict(quantity=name, blocked_by=waiting))
        return out

    def report(self):
        nread = sum(1 for v in self.q.values() if v.status == READ)
        nderv = sum(1 for v in self.q.values() if v.status == DERIVED)
        nunk = sum(1 for v in self.q.values() if not v.known)
        print(f"--- {self.title} ---")
        print(f"quantities: {len(self.q)}   READ {nread}   DERIVED {nderv}   UNKNOWN {nunk}")
        if self.log:
            print("\nderivations:")
            for l in self.log:
                print("  " + l)
        if self.checks:
            print("\nchecks (all inputs known -> residual):")
            for c in self.checks:
                print(f"  {c['constraint']:44s} residual {c['residual']:+8.3f}  [{c['status']}]")
        f = self.frontier()
        if f:
            print(f"\nFRONTIER -- {len(f)} quantity(ies) not determinable from what is known:")
            for item in f:
                blockers = "; ".join(
                    f"{cn} needs {', '.join(o)}" for cn, o in item["blocked_by"] if o)
                print(f"  {item['quantity']}: {blockers or 'no constraint references it'}")
        else:
            print("\nFRONTIER: empty -- everything determinable has been determined.")
        return self


class Constraint:
    name = "constraint"
    vars: list[str] = []
    model: Model = None

    def solve_for(self, target) -> float | None:
        raise NotImplementedError

    def residual(self) -> float | None:
        return None

    def v(self, n):
        return self.model.get(n).value


class SumEquals(Constraint):
    """parts sum to a total: sum(parts) == total"""
    def __init__(self, name, parts, total):
        self.name = name
        self.parts = list(parts)
        self.total = total
        self.vars = self.parts + [total]

    def solve_for(self, target):
        if target == self.total:
            vals = [self.v(p) for p in self.parts]
            if any(x is None for x in vals):
                return None
            return sum(vals)
        others = [p for p in self.parts if p != target]
        vals = [self.v(o) for o in others]
        tot = self.v(self.total)
        if tot is None or any(x is None for x in vals):
            return None
        return tot - sum(vals)

    def residual(self):
        return sum(self.v(p) for p in self.parts) - self.v(self.total)


class Complementary(Constraint):
    """two bearings measured as angles that must sum to 90 degrees"""
    def __init__(self, name, a, b, total=90.0):
        self.name = name
        self.a, self.b, self.total = a, b, total
        self.vars = [a, b]

    def solve_for(self, target):
        other = self.b if target == self.a else self.a
        return self.total - self.v(other)

    def residual(self):
        return (self.v(self.a) + self.v(self.b)) - self.total


class DepthProgression(Constraint):
    """depth_next = depth_prev - run*tan(convergence).
    Ties a lot-depth series to the bearing difference between the two
    bounding lines -- the Cedar Oaks check, generalised."""
    def __init__(self, name, prev, nxt, run, conv_deg):
        self.name = name
        self.prev, self.nxt, self.run, self.conv = prev, nxt, run, conv_deg
        self.vars = [prev, nxt, run, conv_deg]

    def _delta(self):
        return self.v(self.run) * math.tan(math.radians(self.v(self.conv)))

    def solve_for(self, target):
        if target == self.nxt:
            return self.v(self.prev) - self._delta()
        if target == self.prev:
            return self.v(self.nxt) + self._delta()
        if target == self.run:
            d = self.v(self.prev) - self.v(self.nxt)
            t = math.tan(math.radians(self.v(self.conv)))
            return d / t if abs(t) > 1e-12 else None
        if target == self.conv:
            d = self.v(self.prev) - self.v(self.nxt)
            r = self.v(self.run)
            return math.degrees(math.atan2(d, r)) if r else None
        return None

    def residual(self):
        return (self.v(self.prev) - self._delta()) - self.v(self.nxt)


class TraverseClosure(Constraint):
    """A closed figure: the courses must return to the start. Solves a single
    unknown DISTANCE when every bearing and all other distances are known."""
    def __init__(self, name, courses):
        # courses: list of (bearing_deg_name_or_value, distance_var)
        self.name = name
        self.courses = courses
        self.vars = [d for _, d in courses]

    def _az(self, b):
        return b if isinstance(b, (int, float)) else self.v(b)

    def solve_for(self, target):
        n = e = 0.0
        taz = None
        for b, d in self.courses:
            az = self._az(b)
            if d == target:
                taz = az
                continue
            dist = self.v(d)
            if dist is None or az is None:
                return None
            n += dist * math.cos(math.radians(az))
            e += dist * math.sin(math.radians(az))
        if taz is None:
            return None
        # need dist*cos(taz) = -n and dist*sin(taz) = -e
        ct, st = math.cos(math.radians(taz)), math.sin(math.radians(taz))
        if abs(ct) > abs(st):
            return -n / ct
        return -e / st if abs(st) > 1e-12 else None

    def residual(self):
        n = e = 0.0
        for b, d in self.courses:
            az = self._az(b)
            dist = self.v(d)
            n += dist * math.cos(math.radians(az))
            e += dist * math.sin(math.radians(az))
        return math.hypot(n, e)


class CurveRelation(Constraint):
    """L = R*delta(rad); chord = 2R sin(delta/2). Any two give the rest."""
    def __init__(self, name, R, L, delta, chord):
        self.name = name
        self.R, self.L, self.D, self.C = R, L, delta, chord
        self.vars = [R, L, delta, chord]

    def solve_for(self, target):
        R, L, D, C = (self.model.get(x) for x in (self.R, self.L, self.D, self.C))
        if target == self.L and R.known and D.known:
            return R.value * math.radians(D.value)
        if target == self.C and R.known and D.known:
            return 2 * R.value * math.sin(math.radians(D.value) / 2)
        if target == self.R:
            if L.known and D.known:
                return L.value / math.radians(D.value)
            if C.known and D.known:
                return C.value / (2 * math.sin(math.radians(D.value) / 2))
        if target == self.D:
            if L.known and R.known:
                return math.degrees(L.value / R.value)
            if C.known and R.known:
                return 2 * math.degrees(math.asin(min(1, C.value / (2 * R.value))))
        return None

    def residual(self):
        R, L, D, C = (self.v(x) for x in (self.R, self.L, self.D, self.C))
        return R * math.radians(D) - L


class TangentRelation(Constraint):
    """T = R * tan(delta/2). An independent read of the tangent distance is a
    free check on a curve whose R and delta were read separately."""
    def __init__(self, name, R, delta, T):
        self.name = name
        self.R, self.D, self.T = R, delta, T
        self.vars = [R, delta, T]

    def solve_for(self, target):
        R, D, T = (self.model.get(x) for x in (self.R, self.D, self.T))
        if target == self.T and R.known and D.known:
            return R.value * math.tan(math.radians(D.value) / 2)
        if target == self.R and T.known and D.known:
            t = math.tan(math.radians(D.value) / 2)
            return T.value / t if abs(t) > 1e-12 else None
        if target == self.D and R.known and T.known:
            return 2 * math.degrees(math.atan2(T.value, R.value))
        return None

    def residual(self):
        return self.v(self.R) * math.tan(math.radians(self.v(self.D)) / 2) - self.v(self.T)

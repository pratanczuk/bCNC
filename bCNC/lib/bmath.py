#
# Copyright European Organization for Nuclear Research (CERN)
# All rights reserved
#
# Author: Vasilis.Vlachoudis@cern.ch
# Date:   15-May-2004

"""Vector and quadratic operations used by planar geometry."""
from math import sqrt
_accuracy = 1e-15


class Vector(list):
    """Vector class"""

    # ----------------------------------------------------------------------
    def __init__(self, x=3, *args):
        """Create a new vector,
        Vector(size), Vector(list), Vector(x,y,z,...)"""
        list.__init__(self)

        if isinstance(x, int) and not args:
            for i in range(x):
                self.append(0.0)
        elif isinstance(x, (list, tuple)):
            for i in x:
                self.append(float(i))
        else:
            self.append(float(x))
            for i in args:
                self.append(float(i))

    # ----------------------------------------------------------------------
    def set(self, x, y, z=None):
        """Set vector"""
        self[0] = x
        self[1] = y
        if z:
            self[2] = z

    # ----------------------------------------------------------------------
    def __repr__(self):
        return f"[{', '.join([repr(x) for x in self])}]"

    # ----------------------------------------------------------------------
    def __str__(self):
        return "[" + ', '.join([(f"{x:15g}").strip() for x in self]) + "]"

    # ----------------------------------------------------------------------
    def eq(self, v, acc=_accuracy):
        """Test for equality with vector v within accuracy"""
        if len(self) != len(v):
            return False
        s2 = 0.0
        for a, b in zip(self, v):
            s2 += (a - b) ** 2
        return s2 <= acc**2

    # ----------------------------------------------------------------------
    def __eq__(self, v):
        return self.eq(v)

    # ----------------------------------------------------------------------
    def __neg__(self):
        """Negate vector"""
        new = Vector(len(self))
        for i, s in enumerate(self):
            new[i] = -s
        return new

    # ----------------------------------------------------------------------
    def __add__(self, v):
        """Add 2 vectors"""
        size = min(len(self), len(v))
        new = Vector(size)
        for i in range(size):
            new[i] = self[i] + v[i]
        return new

    # ----------------------------------------------------------------------
    def __iadd__(self, v):
        """Add vector v to self"""
        for i in range(min(len(self), len(v))):
            self[i] += v[i]
        return self

    # ----------------------------------------------------------------------
    def __sub__(self, v):
        """Subtract 2 vectors"""
        size = min(len(self), len(v))
        new = Vector(size)
        for i in range(size):
            new[i] = self[i] - v[i]
        return new

    # ----------------------------------------------------------------------
    def __isub__(self, v):
        """Subtract vector v from self"""
        for i in range(min(len(self), len(v))):
            self[i] -= v[i]
        return self

    # ----------------------------------------------------------------------
    # Scale or Dot product
    # ----------------------------------------------------------------------
    def __mul__(self, v):
        """scale*Vector() or Vector()*Vector() - Scale vector or dot product"""
        if isinstance(v, list):
            return self.dot(v)
        else:
            return Vector([x * v for x in self])

    # ----------------------------------------------------------------------
    # Scale or Dot product
    # ----------------------------------------------------------------------
    def __rmul__(self, v):
        """scale*Vector() or Vector()*Vector() - Scale vector or dot product"""
        if isinstance(v, Vector):
            return self.dot(v)
        else:
            return Vector([x * v for x in self])

    # ----------------------------------------------------------------------
    # Divide by floating point
    # ----------------------------------------------------------------------

    def __truediv__(self, b):
        return Vector([x / b for x in self])

    # ----------------------------------------------------------------------
    def __xor__(self, v):
        """Cross product"""
        return self.cross(v)

    # ----------------------------------------------------------------------
    def dot(self, v):
        """Dot product of 2 vectors"""
        s = 0.0
        for a, b in zip(self, v):
            s += a * b

        # Float precision error was causing dot product
        # to be 1.00000000000002 or so...
        s = min(1, s)
        s = max(-1, s)

        return s

    # ----------------------------------------------------------------------
    def cross(self, v):
        """Cross product of 2 vectors"""
        if len(self) == 3:
            return Vector(
                self[1] * v[2] - self[2] * v[1],
                self[2] * v[0] - self[0] * v[2],
                self[0] * v[1] - self[1] * v[0],
            )
        elif len(self) == 2:
            return self[0] * v[1] - self[1] * v[0]
        else:
            raise Exception("Cross product needs 2d or 3d vectors")

    # ----------------------------------------------------------------------
    def length2(self):
        """Return length squared of vector"""
        s2 = 0.0
        for s in self:
            s2 += s**2
        return s2

    # ----------------------------------------------------------------------
    def length(self):
        """Return length of vector"""
        s2 = 0.0
        for s in self:
            s2 += s**2
        return sqrt(s2)

    __abs__ = length

    # ----------------------------------------------------------------------
    def norm(self):
        """Normalize vector and return length"""
        le = self.length()
        if le > 0.0:
            invlen = 1.0 / le
            for _i in range(len(self)):
                self[_i] *= invlen
        return le

    normalize = norm

    # ----------------------------------------------------------------------
    def unit(self):
        """return a unit vector"""
        v = self.clone()
        v.norm()
        return v

    # ----------------------------------------------------------------------
    def clone(self):
        """Clone vector"""
        return Vector(self)

    # ----------------------------------------------------------------------
    def x(self):
        return self[0]

    def y(self):
        return self[1]

    def z(self):
        return self[2]

    # ----------------------------------------------------------------------
    def orthogonal(self):
        """return a vector orthogonal to self"""
        xx = abs(self.x())
        yy = abs(self.y())

        if len(self) >= 3:
            zz = abs(self.z())
            if xx < yy:
                if xx < zz:
                    return Vector(0.0, self.z(), -self.y())
                else:
                    return Vector(self.y(), -self.x(), 0.0)
            else:
                if yy < zz:
                    return Vector(-self.z(), 0.0, self.x())
                else:
                    return Vector(self.y(), -self.x(), 0.0)
        else:
            return Vector(-self.y(), self.x())

    # ----------------------------------------------------------------------
    # Return a random 3D vector
    # ----------------------------------------------------------------------

def quadratic(b, c, eps=_accuracy):
    D = b * b - 4.0 * c
    if D <= 0.0:
        x1 = -0.5 * b  # Always return this as a solution!!!
        if D >= -eps * (b * b + abs(c)):
            return x1, x1
        else:
            return None, None
    else:
        if b > 0.0:
            bD = -b - sqrt(D)
        else:
            bD = -b + sqrt(D)
        return 0.5 * bD, 2.0 * c / bD

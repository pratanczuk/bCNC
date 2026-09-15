#
# Author: vvlachoudis@gmail.com
# Date: 20-Oct-2015

import sys

from Helpers import to_zip


# =============================================================================
# Cardinal cubic spline class
# =============================================================================


# =============================================================================
# Cubic spline ensuring that the first and second derivative are continuous
# adapted from Penelope Manual Appending B.1
# It requires all the points (xi,yi) and the assumption on how to deal
# with the second derivative on the extremeties
# Option 1: assume zero as second derivative on both ends
# Option 2: assume the same as the next or previous one
# =============================================================================


# -----------------------------------------------------------------------------
# Convert a B-spline to polyline with a fixed number of segments
#
# FIXME to become adaptive
# -----------------------------------------------------------------------------
def spline2Polyline(xyz, degree, closed, segments, knots):
    # Check if last point coincide with the first one
    if (bmath.Vector(xyz[0]) - bmath.Vector(xyz[-1])).length2() < 1e-10:
        # it is already closed, treat it as open
        closed = False
        # FIXME we should verify if it is periodic,.... but...
        #       I am not sure :)

    if closed:
        xyz.extend(xyz[:degree])
        knots = None
    else:
        knots.insert(0, 0)

    npts = len(xyz)

    if degree < 1 or degree > 3:
        return None, None, None

    # order:
    k = degree + 1

    if npts < k:
        return None, None, None

    # resolution:
    nseg = segments * npts

    # WARNING: base 1
    b = [0.0] * (npts * 3 + 1)  # polygon points
    h = [1.0] * (npts + 1)  # set all homogeneous weighting factors to 1.0
    p = [0.0] * (nseg * 3 + 1)  # returned curved points

    i = 1
    for pt in xyz:
        b[i] = pt[0]
        b[i + 1] = pt[1]
        b[i + 2] = pt[2]
        i += 3

    if closed:
        _rbsplinu(npts, k, nseg, b, h, p, knots)
    else:
        _rbspline(npts, k, nseg, b, h, p, knots)

    x = []
    y = []
    z = []
    for i in range(1, 3 * nseg + 1, 3):
        x.append(p[i])
        y.append(p[i + 1])
        z.append(p[i + 2])

    return x, y, z


# -----------------------------------------------------------------------------
# Subroutine to generate a B-spline open knot vector with multiplicity
# equal to the order at the ends.
#    c            = order of the basis function
#    n            = the number of defining polygon vertices
#    n+2          = index of x[] for the first occurrence of the maximum knot
#                   vector value
#    n+order      = maximum value of the knot vector -- $n + c$
#    x[]          = array containing the knot vector
# -----------------------------------------------------------------------------
def _knot(n, order):
    x = [0.0] * (n + order + 1)
    for i in range(2, n + order + 1):
        if i > order and i < n + 2:
            x[i] = x[i - 1] + 1.0
        else:
            x[i] = x[i - 1]
    return x


# -----------------------------------------------------------------------------
# Subroutine to generate a B-spline uniform (periodic) knot vector.
#
# order        = order of the basis function
# n            = the number of defining polygon vertices
# n+order      = maximum value of the knot vector -- $n + order$
# x[]          = array containing the knot vector
# -----------------------------------------------------------------------------
def _knotu(n, order):
    x = [0] * (n + order + 1)
    for i in range(2, n + order + 1):
        x[i] = float(i - 1)
    return x


# -----------------------------------------------------------------------------
# Subroutine to generate rational B-spline basis functions--open knot vector

# C code for An Introduction to NURBS
# by David F. Rogers. Copyright (C) 2000 David F. Rogers,
# All rights reserved.

# Name: rbasis
# Subroutines called: none
# Book reference: Chapter 4, Sec. 4. , p 296

#   c        = order of the B-spline basis function
#   d        = first term of the basis function recursion relation
#   e        = second term of the basis function recursion relation
#   h[]      = array containing the homogeneous weights
#   npts     = number of defining polygon vertices
#   nplusc   = constant -- npts + c -- maximum number of knot values
#   r[]      = array containing the rational basis functions
#              r[1] contains the basis function associated with B1 etc.
#   t        = parameter value
#   temp[]   = temporary array
#   x[]      = knot vector
# -----------------------------------------------------------------------------
def _rbasis(c, t, npts, x, h, r):
    nplusc = npts + c
    temp = [0.0] * (nplusc + 1)

    # calculate the first order non-rational basis functions n[i]
    for i in range(1, nplusc):
        if x[i] <= t < x[i + 1]:
            temp[i] = 1.0
        else:
            temp[i] = 0.0

    # calculate the higher order non-rational basis functions
    for k in range(2, c + 1):
        for i in range(1, nplusc - k + 1):
            # if the lower order basis function is zero skip the calculation
            if temp[i] != 0.0:
                d = ((t - x[i]) * temp[i]) / (x[i + k - 1] - x[i])
            else:
                d = 0.0

            # if the lower order basis function is zero skip the calculation
            if temp[i + 1] != 0.0:
                e = ((x[i + k] - t) * temp[i + 1]) / (x[i + k] - x[i + 1])
            else:
                e = 0.0
            temp[i] = d + e

    # pick up last point
    if t >= x[nplusc]:
        temp[npts] = 1.0

    # calculate sum for denominator of rational basis functions
    s = 0.0
    for i in range(1, npts + 1):
        s += temp[i] * h[i]

    # form rational basis functions and put in r vector
    for i in range(1, npts + 1):
        if s != 0.0:
            r[i] = (temp[i] * h[i]) / s
        else:
            r[i] = 0


# -----------------------------------------------------------------------------
# Generates a rational B-spline curve using a uniform open knot vector.
#
# C code for An Introduction to NURBS
# by David F. Rogers. Copyright (C) 2000 David F. Rogers,
# All rights reserved.
#
# Name: rbspline.c
# Subroutines called: _knot, rbasis
# Book reference: Chapter 4, Alg. p. 297
#
#    b           = array containing the defining polygon vertices
#                  b[1] contains the x-component of the vertex
#                  b[2] contains the y-component of the vertex
#                  b[3] contains the z-component of the vertex
#    h           = array containing the homogeneous weighting factors
#    k           = order of the B-spline basis function
#    nbasis      = array containing the basis functions for a single value of t
#    nplusc      = number of knot values
#    npts        = number of defining polygon vertices
#    p[,]        = array containing the curve points
#                  p[1] contains the x-component of the point
#                  p[2] contains the y-component of the point
#                  p[3] contains the z-component of the point
#    p1          = number of points to be calculated on the curve
#    t           = parameter value 0 <= t <= npts - k + 1
#    x[]         = array containing the knot vector
# -----------------------------------------------------------------------------
def _rbspline(npts, k, p1, b, h, p, x):
    nplusc = npts + k
    nbasis = [0.0] * (npts + 1)  # zero and re-dimension the basis array

    # generate the uniform open knot vector
    if x is None or len(x) != nplusc + 1:
        x = _knot(npts, k)
    icount = 0
    # calculate the points on the rational B-spline curve
    t = 0
    step = float(x[nplusc]) / float(p1 - 1)
    for _i1 in range(1, p1 + 1):
        if x[nplusc] - t < 5e-6:
            t = x[nplusc]
        # generate the basis function for this value of t
        nbasis = [0.0] * (
            npts + 1
        )  # zero and re-dimension the knot vector and the basis array
        _rbasis(k, t, npts, x, h, nbasis)
        # generate a point on the curve
        for j in range(1, 4):
            jcount = j
            p[icount + j] = 0.0
            # Do local matrix multiplication
            for i in range(1, npts + 1):
                p[icount + j] += nbasis[i] * b[jcount]
                jcount += 3
        icount += 3
        t += step


# -----------------------------------------------------------------------------
# Subroutine to generate a rational B-spline curve using an uniform periodic
# knot vector
#
# C code for An Introduction to NURBS
# by David F. Rogers. Copyright (C) 2000 David F. Rogers,
# All rights reserved.
#
# Name: rbsplinu.c
# Subroutines called: _knotu, _rbasis
# Book reference: Chapter 4, Alg. p. 298
#
#   b[]         = array containing the defining polygon vertices
#                 b[1] contains the x-component of the vertex
#                 b[2] contains the y-component of the vertex
#                 b[3] contains the z-component of the vertex
#   h[]         = array containing the homogeneous weighting factors
#   k           = order of the B-spline basis function
#   nbasis      = array containing the basis functions for a single value of t
#   nplusc      = number of knot values
#   npts        = number of defining polygon vertices
#   p[,]        = array containing the curve points
#                 p[1] contains the x-component of the point
#                 p[2] contains the y-component of the point
#                 p[3] contains the z-component of the point
#   p1          = number of points to be calculated on the curve
#   t           = parameter value 0 <= t <= npts - k + 1
#   x[]         = array containing the knot vector
# -----------------------------------------------------------------------------
def _rbsplinu(npts, k, p1, b, h, p, x=None):
    nplusc = npts + k
    nbasis = [0.0] * (npts + 1)  # zero and re-dimension the basis array
    # generate the uniform periodic knot vector
    if x is None or len(x) != nplusc + 1:
        # zero and re dimension the knot vector and the basis array
        x = _knotu(npts, k)
    icount = 0
    # calculate the points on the rational B-spline curve
    t = k - 1
    step = (float(npts) - (k - 1)) / float(p1 - 1)
    for i1 in range(1, p1 + 1):
        if x[nplusc] - t < 5e-6:
            t = x[nplusc]
        # generate the basis function for this value of t
        nbasis = [0.0] * (npts + 1)
        _rbasis(k, t, npts, x, h, nbasis)
        # generate a point on the curve
        for j in range(1, 4):
            jcount = j
            p[icount + j] = 0.0
            #  Do local matrix multiplication
            for i in range(1, npts + 1):
                p[icount + j] += nbasis[i] * b[jcount]
                jcount += 3
        icount += 3
        t += step


# =============================================================================

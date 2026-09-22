"""Measure the adult build law on ANSUR II: how BMI, circumferences and limb girth-to-length vary with stature.

    "C:/Program Files/Blender Foundation/Blender 5.2/5.2/python/bin/python.exe" derive_girth_law.py

Prints what `humanform.species_design` keeps as GIRTH_LAW and LIMB_BAND (it writes nothing). Per sex, by
log-log least squares on the 4,082 men and 1,986 women of ANSUR II (data/sources/ansur2):

- weight ~ H^p (the Benn index) and the correlation of BMI with stature: is BMI stature-free among adults?
- each circumference ~ H^a BMI^b: how a girth grows with stature at a fixed BMI (a = 1 would be geometric);
- each limb's circumference over its length, c/L ~ H^aH BMI^aB, with the 5th and 95th percentile of the
  residual (the spread at a given stature and BMI), which is the adult band a species limb is checked against.

Limb lengths are joint to joint as humancheck measures them: thigh = trochanterion - lateral femoral
epicondyle height, shin = epicondyle - lateral malleolus height, upper arm = shoulder-elbow length, forearm =
radiale-stylion length. ANSUR's biceps and forearm circumferences are flexed.
"""

import csv
import os

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "data", "sources", "ansur2")


def main():
    for sex in ("male", "female"):
        with open(os.path.join(SRC, f"ANSUR_II_{sex.upper()}_Public.csv"), encoding="latin-1", newline="") as fh:
            rows = list(csv.DictReader(fh))

        def g(k):
            return np.array([float(r[k]) for r in rows]) / 1000.0
        H = g("stature")
        W = np.array([float(r["weightkg"]) for r in rows]) / 10.0
        bmi = W / H ** 2
        lH, lB = np.log(H), np.log(bmi)
        X = np.column_stack([np.ones_like(lH), lH, lB])
        p = np.polyfit(lH, np.log(W), 1)[0]
        print(f"{sex}: n {len(rows)}, weight ~ H^{p:.2f}, corr(BMI, H) {np.corrcoef(bmi, H)[0, 1]:+.3f}, "
              f"BMI mean {bmi.mean():.1f} (p5 {np.percentile(bmi, 5):.1f}, p95 {np.percentile(bmi, 95):.1f}), "
              f"H mean {H.mean():.3f}")
        for name, c in (("thigh", g("thighcircumference")), ("calf", g("calfcircumference")),
                        ("biceps_flexed", g("bicepscircumferenceflexed")),
                        ("forearm_flexed", g("forearmcircumferenceflexed")), ("neck", g("neckcircumference")),
                        ("chest_depth", g("chestdepth")), ("chest_breadth", g("chestbreadth")),
                        ("bideltoid", g("bideltoidbreadth")), ("hip_breadth", g("hipbreadth"))):
            a, b = np.linalg.lstsq(X, np.log(c), rcond=None)[0][1:]
            print(f"  {name:15} ~ H^{a:.2f} BMI^{b:.2f}")
        limbs = {"thigh": (g("thighcircumference"), g("trochanterionheight") - g("lateralfemoralepicondyleheight")),
                 "shin": (g("calfcircumference"), g("lateralfemoralepicondyleheight") - g("lateralmalleolusheight")),
                 "upper_arm": (g("bicepscircumferenceflexed"), g("shoulderelbowlength")),
                 "forearm": (g("forearmcircumferenceflexed"), g("radialestylionlength"))}
        for name, (c, L) in limbs.items():
            r = c / L
            co, *_ = np.linalg.lstsq(X, np.log(r), rcond=None)
            res = np.log(r) - X @ co
            at = float(np.exp(co[0] + co[1] * np.log(H.mean()) + co[2] * np.log(bmi.mean())))
            print(f"  {name:9} c/L {at:.3f} at H {H.mean():.3f} BMI {bmi.mean():.1f}; ~ H^{co[1]:.2f} BMI^{co[2]:.2f}; "
                  f"residual p5 {np.exp(np.percentile(res, 5)):.3f} p95 {np.exp(np.percentile(res, 95)):.3f}")
        dbr = g("chestdepth") / g("chestbreadth")
        co = np.linalg.lstsq(X, np.log(dbr), rcond=None)[0]
        print(f"  chest depth/breadth mean {dbr.mean():.3f} (p5 {np.percentile(dbr, 5):.3f}, p95 "
              f"{np.percentile(dbr, 95):.3f}); ~ H^{co[1]:.2f} BMI^{co[2]:.2f}")


if __name__ == "__main__":
    main()

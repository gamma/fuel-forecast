import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parents[1]/"fuel-forecast-skill"/"scripts"))
from model import (FEATURE_NAMES, confidence, constrain_bootstrap_asymmetry,
                   feature_vector, new_model, predict, update)
def test_learning():
    m=new_model(2)
    x=[0.0] * len(FEATURE_NAMES)
    x[0] = 1.0
    x[2] = -0.5
    x[-1] = 1.0
    p1=predict(m,x)
    for _ in range(20):
        update(m,x,-5.0)
    p2=predict(m,x)
    assert abs(-5-p2) < abs(-5-p1)

def test_rockets_and_feathers_features():
    rise = feature_vector(
        "2026-04-01", brent_eur_d1=5.0, distillate_eur_d5=10.0
    )
    fall = feature_vector(
        "2026-04-01", brent_eur_d1=-5.0, distillate_eur_d5=-10.0
    )
    names = {name: i for i, name in enumerate(FEATURE_NAMES)}
    assert rise[names["brent_eur_1d_up"]] == 1.0
    assert rise[names["brent_eur_1d_down"]] == 0.0
    assert fall[names["brent_eur_1d_up"]] == 0.0
    assert fall[names["brent_eur_1d_down"]] == -1.0
    assert rise[names["distillate_eur_5d_up"]] == 1.0
    assert fall[names["distillate_eur_5d_down"]] == -1.0

def test_asymmetric_prior():
    names = {name: i for i, name in enumerate(FEATURE_NAMES)}
    one_day = new_model(1)["weights"]
    four_day = new_model(4)["weights"]
    up = names["distillate_eur_1d_up"]
    down = names["distillate_eur_1d_down"]
    assert one_day[up] > one_day[down]
    assert four_day[down] > one_day[down]

    projected = list(one_day)
    projected[up] = -2.0
    projected[down] = 4.0
    projected = constrain_bootstrap_asymmetry(projected, 1)
    assert projected[up] == 0.0
    assert projected[down] == 0.0

def test_bootstrap_confidence_cap():
    model = new_model(1)
    model["bootstrap_samples"] = 144
    model["mae_ema_ct"] = 1.2
    assert confidence(model) == 0.62

if __name__=="__main__":
    test_learning()
    test_rockets_and_feathers_features()
    test_asymmetric_prior()
    test_bootstrap_confidence_cap()
    print("OK")

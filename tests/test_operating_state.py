from rod_ia.domain.models.hotel import HotelOperatingState


def test_operating_state_recomputes_clients_mois():
    state = HotelOperatingState(nb_chambres=100, taux_occupation=0.8, guests_per_chambre=2.0)
    assert round(state.clients_mois, 1) == round(100 * 0.8 * 2.0 * 30.5, 1)


def test_operating_state_accepts_percent_to():
    state = HotelOperatingState(nb_chambres=100, taux_occupation=80)
    assert state.taux_occupation == 0.8
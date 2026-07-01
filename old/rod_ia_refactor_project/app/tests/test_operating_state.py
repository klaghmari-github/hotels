from app.domain.models.hotel import HotelOperatingState

def test_to_updates_clients():
    s = HotelOperatingState(nb_chambres=100, taux_occupation=0.5, guests_per_chambre=2)
    assert s.chambres_occupees == 50
    assert s.clients_jour == 100
    s.taux_occupation = 0.8
    assert s.chambres_occupees == 80
    assert s.clients_jour == 160

def test_clients_updates_to():
    s = HotelOperatingState(nb_chambres=100, taux_occupation=0.5, guests_per_chambre=2)
    s.clients_jour = 120
    assert abs(s.taux_occupation - 0.6) < 1e-9

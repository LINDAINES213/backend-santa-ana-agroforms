from django.urls import reverse
from django.test import Client

def test_admin_index_redirects_to_login():
    client = Client()
    r = client.get(reverse('admin:index'))
    assert r.status_code in (302, 301)

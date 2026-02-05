import io
from recon.utils import normalize_header, is_valid_ip, is_valid_hostname, read_csv


def test_normalize_header():
    assert normalize_header('IP Address') == 'ip_address'
    assert normalize_header('Host-Name') == 'host_name'


def test_ip_validation():
    assert is_valid_ip('10.0.0.1')
    assert is_valid_ip('10.0.0.1/32')
    assert not is_valid_ip('999.0.0.1')


def test_hostname_validation():
    assert is_valid_hostname('server-01')
    assert is_valid_hostname('a.b.c')
    assert not is_valid_hostname('-bad')


def test_read_csv_with_bom(tmp_path):
    content = '\ufeffitam_id,hostname,ip_address\n1,host,10.0.0.1\n'
    f = tmp_path / 'test.csv'
    f.write_text(content, encoding='utf-8')

    class Dummy:
        filename = 'test.csv'
        def read(self):
            return f.read_bytes()

    rows, headers = read_csv(Dummy())
    assert headers == ['itam_id', 'hostname', 'ip_address']
    assert rows[0]['hostname'] == 'host'

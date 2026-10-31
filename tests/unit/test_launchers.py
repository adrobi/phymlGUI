import dataclasses

import pytest

from phyml_core.launchers import Mpi, Native


def test_native_returns_the_argv_unchanged():
    argv = ['phyml.exe', '-i', 'a.phy']
    assert Native().wrap(argv) == argv


def test_native_does_not_alias_the_input_list():
    argv = ['x']
    wrapped = Native().wrap(argv)
    wrapped.append('y')
    assert argv == ['x']


def test_mpi_prefixes_mpiexec_np_and_the_argv():
    assert Mpi('C:/MPI/mpiexec.exe', 4).wrap(['phyml.exe', '-i', 'a.phy']) == [
        'C:/MPI/mpiexec.exe', '-np', '4', 'phyml.exe', '-i', 'a.phy']


def test_mpi_formats_np_as_a_string():
    assert Mpi('mpiexec', 2).wrap([])[2] == '2'


def test_launchers_compare_by_value_and_are_immutable():
    assert Native() == Native()
    assert Mpi('m', 2) == Mpi('m', 2) and Mpi('m', 2) != Mpi('m', 3)
    with pytest.raises(dataclasses.FrozenInstanceError):
        Mpi('m', 2).np = 3

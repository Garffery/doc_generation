from doc_generation import main


def test_main(capsys):
    main()
    captured = capsys.readouterr()
    assert "doc_generation is ready" in captured.out

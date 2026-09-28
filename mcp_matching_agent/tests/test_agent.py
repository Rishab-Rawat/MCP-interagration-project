from matching_agent import extract_requirements, rank_documents


def test_extract_requirements():
    req = extract_requirements("React developer with 3+ years experience and Node.js")
    assert "react" in req["must_have"]
    assert "node.js" in req["must_have"]
    assert req["min_years"] == 3


def test_rank_documents():
    req = {"must_have": ["react", "javascript"], "nice_to_have": [], "min_years": 3}
    docs = [
        {"filename": "a.txt", "content": "5 years React JavaScript"},
        {"filename": "b.txt", "content": "1 year React"},
    ]
    ranked, _ = rank_documents(req, docs)
    assert ranked[0]["candidate_id"] == "a"

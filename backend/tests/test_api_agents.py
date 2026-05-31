from app.routes.api.agents import AgentActRequest, _act_url


def test_act_url_normalizes_runtime_endpoint():
    assert _act_url("") == ""
    assert _act_url("http://localhost:5060") == "http://localhost:5060/act"
    assert _act_url("http://localhost:5060/act") == "http://localhost:5060/act"
    assert _act_url("http://localhost:5060/") == "http://localhost:5060/act"


def test_agent_act_request_does_not_share_mutable_defaults():
    first = AgentActRequest()
    second = AgentActRequest()

    first.history.append({"role": "user"})
    first.context["x"] = 1

    assert second.history == []
    assert second.context == {}

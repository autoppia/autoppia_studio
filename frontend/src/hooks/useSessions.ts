import { useState, useEffect } from "react";
import { useSelector } from "react-redux";
import { SessionItem } from "../utils/types";
import { getApiUrl } from "../utils/api-url";

const apiUrl = getApiUrl();

export default function useSessions() {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [filteredSessions, setFilteredSessions] = useState<SessionItem[]>([]);
  const [searchString, setSearchString] = useState("");
  const [loading, setLoading] = useState(true);

  const email = useSelector((state: any) => state.user.email);
  const [companyId, setCompanyId] = useState(localStorage.getItem("automata_company_id") || "");

  useEffect(() => {
    const handler = (event: Event) => {
      setCompanyId((event as CustomEvent).detail?.companyId ?? localStorage.getItem("automata_company_id") ?? "");
    };
    window.addEventListener("automata-company-changed", handler);
    return () => window.removeEventListener("automata-company-changed", handler);
  }, []);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const params = new URLSearchParams({ email });
        if (companyId) params.set("companyId", companyId);
        const response = await fetch(`${apiUrl}/sessions?${params.toString()}`);
        const data = await response.json();
        setSessions(data.sessions || []);
        setFilteredSessions(data.sessions || []);
      } catch (err) {
        console.error(err);
      } finally {
        setLoading(false);
      }
    }
    if (email) fetchData();
  }, [email, companyId]);

  useEffect(() => {
    if (!searchString) {
      setFilteredSessions(sessions);
      return;
    }
    const filtered = sessions.filter(
      (item) =>
        item.prompt.toLowerCase().includes(searchString.toLowerCase()) ||
        item.initialUrl.toLowerCase().includes(searchString.toLowerCase())
    );
    setFilteredSessions(filtered);
  }, [searchString, sessions]);

  return { sessions, filteredSessions, searchString, setSearchString, loading };
}

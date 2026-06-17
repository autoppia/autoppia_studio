import { useState, useEffect } from "react";
import { useSelector } from "react-redux";
import { SessionItem } from "../utils/types";

const apiUrl = (process.env.REACT_APP_API_URL || "http://127.0.0.1:8080");

export default function useSessions() {
  const [sessions, setSessions] = useState<SessionItem[]>([]);
  const [filteredSessions, setFilteredSessions] = useState<SessionItem[]>([]);
  const [searchString, setSearchString] = useState("");
  const [loading, setLoading] = useState(true);

  const email = useSelector((state: any) => state.user.email);

  useEffect(() => {
    async function fetchData() {
      try {
        setLoading(true);
        const response = await fetch(`${apiUrl}/sessions?email=${email}`);
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
  }, [email]);

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

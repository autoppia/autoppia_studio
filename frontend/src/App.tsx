import { useEffect } from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { useDispatch } from "react-redux";
import { jwtDecode } from "jwt-decode";
import Cookies from "js-cookie";
import "./App.css";

import Home from "./pages/home";
import Operator from "./pages/operator";
import { setUser } from "./redux/userSlice";

const apiUrl = process.env.REACT_APP_API_URL;

function App() {
  const dispatch = useDispatch();

  useEffect(() => {
    const fetchData = async () => {
      try {
        const accessToken = Cookies.get("access_token");
        if (!accessToken) {
          return;
        }
        const decodedToken = jwtDecode(accessToken!) as any;
        const email = decodedToken.email;
        const response = await fetch(`${apiUrl}/user?email=${email}`);
        if (response.ok) {
          const data = await response.json();
          dispatch(
            setUser({
              email: data.user.email,
              instructions: data.user.instructions,
            })
          );
        }
      } catch (err) {
        console.error(err);
      }
    };
    fetchData();
  }, [dispatch]);

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/operator" element={<Operator />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;

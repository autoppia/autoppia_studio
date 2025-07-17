const express = require('express');  
const history = require("connect-history-api-fallback");

const app = express();  
const PORT = process.env.PORT || 3000;  

app.use(history());
app.use("/", express.static("./build"));

app.listen(PORT, () => {  
  console.log(`Server is running on http://localhost:${PORT}`);  
});  
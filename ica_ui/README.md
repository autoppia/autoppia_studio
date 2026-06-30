# ICA UI

Standalone UI for Infinite Company Arena / CompanyHarvester benchmarks.

This app is intentionally separate from the main Autoppia Studio frontend. It is
a static cockpit that talks to the Studio backend ICA API:

- `GET /ica/harvesters`
- `GET /ica/demo-companies`
- `GET /ica/runs`
- `POST /ica/runs`

## Run

```bash
cd ica_ui
npm run dev
```

Default URL:

```text
http://127.0.0.1:3100
```

Default API:

```text
http://127.0.0.1:8080
```

You can override the UI port with `ICA_UI_PORT` and the API URL from the input
in the top bar or with:

```text
http://127.0.0.1:3100?api=http://127.0.0.1:8080
```

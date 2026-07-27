# API Overview

All endpoints are prefixed with `/api`.

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/auth/register` | POST | Register a new user |
| `/auth/token` | POST | Login and receive JWT |
| `/auth/me` | GET | Current user profile |
| `/projects/` | GET/POST | List/create projects |
| `/projects/{id}` | GET/DELETE | Get/delete project |
| `/files/{project_id}` | GET | List uploaded files |
| `/files/{project_id}/upload` | POST | Upload a file |
| `/files/{file_id}` | DELETE | Delete a file |
| `/import/{file_id}/preview` | GET | Preview a file/sheet |
| `/import/{file_id}/map` | POST | Save column mapping |
| `/import/{file_id}/import` | POST | Import as dataset |
| `/analysis/{project_id}/datasets` | GET | List datasets |
| `/analysis/{project_id}/dataset/{id}` | GET | Get dataset |
| `/analysis/{project_id}/dataset/{id}/preprocess` | POST | Preprocess dataset |
| `/stats/{project_id}/dataset/{id}/stats` | POST | Run statistical test |
| `/plots/{project_id}/dataset/{id}/plot` | POST | Generate Plotly figure |
| `/isotope/{project_id}/dataset/{id}/isotope` | POST | Run isotope analysis |
| `/pathways/{project_id}/dataset/{id}/pathway` | POST | Build pathway figure |

See `/docs` on a running backend for full OpenAPI documentation.

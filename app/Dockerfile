# wardenIQ application image.
#
# Build context is the REPO ROOT (see docker-compose.app.yml) so this Dockerfile
# can compile the React frontend and bake the result into the Python image. That
# means `./run.sh` (docker compose up --build) ships a ready-to-serve SPA — no
# Node on the host and no separate `npm run dev` needed.

# ---- Stage 1: build the React SPA (frontend/ -> app/static-react) ----
FROM node:20-slim AS frontend
WORKDIR /build/frontend
# Install deps first for layer caching.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
# Then the source, and build. Vite's outDir is ../app/static-react, so the output
# lands at /build/app/static-react.
COPY frontend/ ./
RUN npm run build

# ---- Stage 2: the FastAPI app ----
FROM python:3.11-slim
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ .
# Copy the compiled SPA from the frontend stage (app/static-react is .dockerignored
# from the build context, so this fresh build is the only copy in the image).
COPY --from=frontend /build/app/static-react ./static-react
EXPOSE 8001
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]

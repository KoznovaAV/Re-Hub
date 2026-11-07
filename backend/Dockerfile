FROM golang:1.25-alpine AS build
WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -o /rehub-api ./cmd/api

FROM alpine:3.23
COPY --from=build /rehub-api /usr/local/bin/rehub-api
USER 65534:65534
EXPOSE 8080
ENTRYPOINT ["/usr/local/bin/rehub-api"]

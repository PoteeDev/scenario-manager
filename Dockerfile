FROM golang:1.21-alpine as build
WORKDIR /build
COPY go.* ./
RUN go mod download
COPY src/ src/
RUN CGO_ENABLED=0 GOOS=linux go build -o manager ./src

FROM alpine:3
WORKDIR /app
COPY --from=build /build/manager .
CMD ["./manager"]
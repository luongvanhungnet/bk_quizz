FROM eclipse-temurin:17-jdk-jammy AS build
WORKDIR /workspace
COPY .mvn .mvn
COPY mvnw mvnw
COPY pom.xml pom.xml
RUN chmod +x mvnw && ./mvnw -B -DskipTests dependency:go-offline
COPY src src
RUN ./mvnw -B -DskipTests package

FROM eclipse-temurin:17-jre-jammy
RUN groupadd --system bkquiz && useradd --system --gid bkquiz --home-dir /app bkquiz
WORKDIR /app
COPY --from=build /workspace/target/*.jar app.jar
USER bkquiz
EXPOSE 8080
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=75", "-Dfile.encoding=UTF-8", "-jar", "/app/app.jar"]


import { expect, test } from "@playwright/test";
import path from "node:path";

test("registro, proyecto, subida y análisis end-to-end (§18)", async ({ page }) => {
  const stamp = Date.now();
  const email = `e2e-${stamp}@example.com`;
  const projectName = `Proyecto E2E ${stamp}`;

  await page.goto("/");
  await expect(page.getByText("Acceso")).toBeVisible();

  await page.getByLabel("Correo").fill(email);
  await page.getByLabel("Contraseña").fill("supersecret123");
  await page.getByLabel("Nombre").fill("E2E");
  await page.getByLabel("Organización").fill(`Org E2E ${stamp}`);
  await page.getByRole("button", { name: "Crear cuenta" }).click();

  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByRole("heading", { name: "Proyectos" })).toBeVisible();
  await expect(page.getByText("Uso de la organización")).toBeVisible();

  await page.getByPlaceholder("Nombre").fill(projectName);
  await page.getByRole("button", { name: "Crear" }).click();
  await expect(page.getByText(projectName)).toBeVisible();

  await page.getByText(projectName).click();
  await expect(page.getByRole("heading", { name: projectName })).toBeVisible();

  const fixture = path.join(__dirname, "fixtures", "sample-project.zip");
  await page.locator('input[type="file"]').setInputFiles(fixture);
  await page.getByRole("button", { name: "Subir ZIP" }).click();
  await expect(page.getByText(/sample-project\.zip/)).toBeVisible();

  await page.getByRole("button", { name: "Iniciar análisis" }).click();
  await expect(page.getByRole("heading", { name: "3. Resultados" })).toBeVisible();
  await expect(page.getByText("COMPLETED").first()).toBeVisible({ timeout: 90_000 });

  await expect(page.getByRole("heading", { name: "Hallazgos" })).toBeVisible();
  await expect(page.getByText("Grafo de arquitectura")).toBeVisible();
  await expect(page.getByText("Análisis de binarios")).toBeVisible();

  page.on("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Eliminar proyecto" }).click();
  await expect(page).toHaveURL(/\/dashboard/);
  await expect(page.getByText(projectName)).toHaveCount(0);
});

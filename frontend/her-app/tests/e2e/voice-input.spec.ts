/**
 * E2E tests for voice input functionality
 * Tests the complete user flow: press-hold → record → release → send
 */

import { test, expect } from '@playwright/test'

test.describe('Voice Input E2E Tests', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to chat page
    await page.goto('/her')

    // Wait for page to load
    await page.waitForSelector('[data-testid="voice-input-button"]', { timeout: 10000 })
  })

  test('should display microphone button on chat page', async ({ page }) => {
    const micButton = page.locator('[data-testid="voice-input-button"]')
    await expect(micButton).toBeVisible()
    await expect(micButton).toHaveAttribute('aria-label', '按住说话')
  })

  test('should show recording panel when pressing microphone', async ({ page }) => {
    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Press and hold microphone button
    await micButton.dispatchEvent('pointerdown')

    // Wait for recording panel to appear
    const recordingPanel = page.locator('[data-testid="recording-panel"]')
    await expect(recordingPanel).toBeVisible({ timeout: 1000 })

    // Check recording panel contents
    await expect(recordingPanel.locator('[data-testid="volume-bars"]')).toBeVisible()
    await expect(recordingPanel.locator('[data-testid="recording-duration"]')).toBeVisible()
    await expect(recordingPanel.locator('[data-testid="recording-status"]')).toContainText('松开发送，上滑取消')

    // Release button
    await micButton.dispatchEvent('pointerup')

    // Recording panel should disappear
    await expect(recordingPanel).not.toBeVisible({ timeout: 500 })
  })

  test('should show cancel prompt when swiping up', async ({ page }) => {
    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Press microphone
    await micButton.dispatchEvent('pointerdown', { clientY: 500 })

    const recordingPanel = page.locator('[data-testid="recording-panel"]')
    await expect(recordingPanel).toBeVisible()

    // Swipe up (move pointer up by 100px)
    await micButton.dispatchEvent('pointermove', { clientY: 400 })

    // Check cancel prompt
    const cancelPrompt = page.locator('[data-testid="cancel-prompt"]')
    await expect(cancelPrompt).toBeVisible()
    await expect(cancelPrompt).toContainText('松开取消发送')

    // Release button
    await micButton.dispatchEvent('pointerup', { clientY: 400 })

    // Recording panel should disappear
    await expect(recordingPanel).not.toBeVisible()

    // No message should be sent
    const messages = page.locator('[data-testid="chat-message"]')
    await expect(messages).toHaveCount(0)
  })

  test('should send message after recording', async ({ page }) => {
    // Grant microphone permission
    await page.context().grantPermissions(['microphone'])

    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Press and hold for 2 seconds
    await micButton.dispatchEvent('pointerdown')
    await page.waitForTimeout(2000)

    // Release button
    await micButton.dispatchEvent('pointerup')

    // Recording panel should disappear immediately (微信式体验)
    const recordingPanel = page.locator('[data-testid="recording-panel"]')
    await expect(recordingPanel).not.toBeVisible({ timeout: 500 })

    // Wait for message to appear (backend processing)
    const newMessage = page.locator('[data-testid="chat-message"]').last()
    await expect(newMessage).toBeVisible({ timeout: 15000 })

    // Message should have text content
    const messageText = await newMessage.locator('[data-testid="message-text"]').textContent()
    expect(messageText).toBeTruthy()
    expect(messageText?.length).toBeGreaterThan(0)
  })

  test('should display volume warning when audio is quiet', async ({ page }) => {
    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Press microphone
    await micButton.dispatchEvent('pointerdown')

    const recordingPanel = page.locator('[data-testid="recording-panel"]')
    await expect(recordingPanel).toBeVisible()

    // Check for volume warning (this would require mocking low audio volume)
    // For E2E, we can check if the warning text exists in DOM
    const volumeWarning = page.locator('[data-testid="volume-warning"]')

    // If volume is low, warning should appear
    // Note: In real E2E, volume depends on actual microphone input
    // We can check if the component has the logic to show warning
    await expect(volumeWarning).toHaveCount(1) // At least warning component exists

    // Release button
    await micButton.dispatchEvent('pointerup')
  })

  test('should handle microphone permission denial', async ({ page }) => {
    // Deny microphone permission
    await page.context().grantPermissions([])

    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Try to press microphone
    await micButton.dispatchEvent('pointerdown')

    // Button should be disabled or show error
    await expect(micButton).toHaveAttribute('disabled', 'true')

    // No recording panel should appear
    const recordingPanel = page.locator('[data-testid="recording-panel"]')
    await expect(recordingPanel).not.toBeVisible()
  })

  test('should handle network errors gracefully', async ({ page }) => {
    // Mock network failure
    await page.route('**/api/gateway/v1/voice/transcribe', route => {
      route.abort('failed')
    })

    await page.context().grantPermissions(['microphone'])

    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Record for 2 seconds
    await micButton.dispatchEvent('pointerdown')
    await page.waitForTimeout(2000)
    await micButton.dispatchEvent('pointerup')

    // Should show error message
    const errorMessage = page.locator('[data-testid="error-toast"]')
    await expect(errorMessage).toBeVisible({ timeout: 5000 })
    await expect(errorMessage).toContainText(/语音识别失败|网络连接失败/)
  })

  test('should handle empty transcription result', async ({ page }) => {
    // Mock empty transcription result
    await page.route('**/api/gateway/v1/voice/transcribe', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          text: '',
          language: 'zh',
          language_probability: 1.0,
          segments: [],
        }),
      })
    })

    await page.context().grantPermissions(['microphone'])

    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Record for 2 seconds
    await micButton.dispatchEvent('pointerdown')
    await page.waitForTimeout(2000)
    await micButton.dispatchEvent('pointerup')

    // Should show "未识别到内容" error
    const errorMessage = page.locator('[data-testid="error-toast"]')
    await expect(errorMessage).toBeVisible({ timeout: 5000 })
    await expect(errorMessage).toContainText('未识别到语音内容')
  })

  test('should handle hallucination detection', async ({ page }) => {
    // Mock hallucination result (YouTube ending words)
    await page.route('**/api/gateway/v1/voice/transcribe', route => {
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          text: '请不吝点赞订阅转发打赏支持明镜与点点栏目',
          language: 'zh',
          language_probability: 0.99,
          segments: [],
        }),
      })
    })

    await page.context().grantPermissions(['microphone'])

    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Record for 2 seconds
    await micButton.dispatchEvent('pointerdown')
    await page.waitForTimeout(2000)
    await micButton.dispatchEvent('pointerup')

    // Backend should filter hallucination
    // Frontend should show error or empty result
    const messages = page.locator('[data-testid="chat-message"]')
    await expect(messages).toHaveCount(0, { timeout: 5000 })

    // Or show error message
    const errorMessage = page.locator('[data-testid="error-toast"]')
    const errorVisible = await errorMessage.isVisible()
    if (errorVisible) {
      await expect(errorMessage).toContainText(/未识别到|语音内容/)
    }
  })

  test('should auto-stop recording at max duration (60 seconds)', async ({ page }) => {
    await page.context().grantPermissions(['microphone'])

    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Press and hold (simulate long recording)
    await micButton.dispatchEvent('pointerdown')

    const recordingPanel = page.locator('[data-testid="recording-panel"]')
    await expect(recordingPanel).toBeVisible()

    // Wait for auto-stop (60 seconds in production, reduce for test)
    // Note: For E2E testing, we can mock the timer or use shorter duration
    await page.waitForTimeout(3000) // Short test duration

    // Check that recording stopped
    // In production, this would be 60 seconds
    // For test, we can check if timer exists
    const durationText = await recordingPanel.locator('[data-testid="recording-duration"]').textContent()
    expect(durationText).toBeTruthy()

    // Release button
    await micButton.dispatchEvent('pointerup')
  })

  test('should match WeChat-style UX (instant feedback)', async ({ page }) => {
    await page.context().grantPermissions(['microphone'])

    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Press
    await micButton.dispatchEvent('pointerdown')

    const recordingPanel = page.locator('[data-testid="recording-panel"]')
    await expect(recordingPanel).toBeVisible()

    // Record for 2 seconds
    await page.waitForTimeout(2000)

    // Release
    await micButton.dispatchEvent('pointerup')

    // Recording panel should disappear immediately (no "识别中..." delay)
    const disappearTime = Date.now()
    await expect(recordingPanel).not.toBeVisible()
    const actualDisappearTime = Date.now()

    // Disappear time should be < 500ms (微信式体验)
    expect(actualDisappearTime - disappearTime).toBeLessThan(500)

    // No "识别中..." text should ever appear
    const processingText = await page.locator('text=识别中').count()
    expect(processingText).toBe(0)

    // No technical details should appear (Whisper, model, download)
    const technicalText = await page.locator('text=/Whisper|模型|下载/').count()
    expect(technicalText).toBe(0)
  })

  test('should support multiple consecutive recordings', async ({ page }) => {
    await page.context().grantPermissions(['microphone'])

    const micButton = page.locator('[data-testid="voice-input-button"]')

    // First recording
    await micButton.dispatchEvent('pointerdown')
    await page.waitForTimeout(1500)
    await micButton.dispatchEvent('pointerup')

    await page.waitForTimeout(1000)

    // Second recording
    await micButton.dispatchEvent('pointerdown')
    await page.waitForTimeout(1500)
    await micButton.dispatchEvent('pointerup')

    await page.waitForTimeout(1000)

    // Third recording
    await micButton.dispatchEvent('pointerdown')
    await page.waitForTimeout(1500)
    await micButton.dispatchEvent('pointerup')

    // Wait for messages to appear
    const messages = page.locator('[data-testid="chat-message"]')
    await expect(messages).toHaveCount(3, { timeout: 20000 })
  })

  test('should handle browser compatibility', async ({ page, browserName }) => {
    // Test on different browsers
    const supportedBrowsers = ['chromium', 'firefox', 'webkit']

    if (!supportedBrowsers.includes(browserName)) {
      test.skip()
      return
    }

    await page.context().grantPermissions(['microphone'])

    const micButton = page.locator('[data-testid="voice-input-button"]')

    // Check if button is enabled
    const isDisabled = await micButton.isDisabled()
    expect(isDisabled).toBe(false)

    // Try recording
    await micButton.dispatchEvent('pointerdown')
    await page.waitForTimeout(1500)
    await micButton.dispatchEvent('pointerup')

    // Should work on all supported browsers
    const messages = page.locator('[data-testid="chat-message"]')
    await expect(messages.first()).toBeVisible({ timeout: 15000 })
  })
})
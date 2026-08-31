package com.example.btcalarm

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        val etAlvo = findViewById<EditText>(R.id.etAlvo)
        val btnDefinir = findViewById<Button>(R.id.btnDefinir)

        btnDefinir.setOnClickListener {
            val textoAlvo = etAlvo.text.toString()

            if (textoAlvo.isNotEmpty()) {
                val valorAlvo = textoAlvo.toDouble()
                enviarAlvoParaRender(valorAlvo)
            } else {
                Toast.makeText(this, "Digite um valor para o alvo", Toast.LENGTH_SHORT).show()
            }
        }
    }

    private fun enviarAlvoParaRender(valorAlvo: Double) {
        thread {
            try {
                val url = URL("https://btc-alarm-api.onrender.com/configurar_alarme")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json; utf-8")
                conn.doOutput = true

                val jsonPayload = """
                    {
                        "preco_alvo": $valorAlvo,
                        "fcm_token": ""
                    }
                """.trimIndent()

                OutputStreamWriter(conn.outputStream, "UTF-8").use { os ->
                    os.write(jsonPayload)
                    os.flush()
                }

                val responseCode = conn.responseCode
                runOnUiThread {
                    if (responseCode == 200) {
                        Toast.makeText(this, "Alvo de USD $valorAlvo enviado com sucesso!", Toast.LENGTH_SHORT).show()
                    } else {
                        Toast.makeText(this, "Erro no servidor: Código $responseCode", Toast.LENGTH_SHORT).show()
                    }
                }
                conn.disconnect()
            } catch (e: Exception) {
                e.printStackTrace()
                runOnUiThread {
                    Toast.makeText(this, "Falha de conexão com o Render", Toast.LENGTH_SHORT).show()
                }
            }
        }
    }
}
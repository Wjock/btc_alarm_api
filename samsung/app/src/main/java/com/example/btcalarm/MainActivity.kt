package com.example.btcalarm

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Color
import android.media.RingtoneManager
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import com.google.firebase.messaging.FirebaseMessaging
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class MainActivity : AppCompatActivity() {

    private lateinit var tvPrecoAtual: TextView
    private lateinit var tvStatusAlarme: TextView
    private val handler = Handler(Looper.getMainLooper())
    private var runnableAtualizacao: Runnable? = null
    
    private var precoAlvoAtual: Double = 0.0
    private var precoInicialAlarme: Double = 0.0
    private var alarmeAtivo: Boolean = false
    private var ultimoPrecoConhecido: Double = 0.0

    // Receiver para capturar o disparo enviado pelo Firebase em tempo real
    private val fcmReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            if (alarmeAtivo) {
                dispararAlarmeAtingido()
            }
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContentView(R.layout.activity_main)

        tvPrecoAtual = findViewById(R.id.tvPrecoAtual)
        tvStatusAlarme = findViewById(R.id.tvStatusAlarme)
        val etAlvo = findViewById<EditText>(R.id.etAlvo)
        val btnDefinir = findViewById<Button>(R.id.btnDefinir)

        carregarEstadoAlarme()
        obterERegistrarTokenFcm()

        btnDefinir.setOnClickListener {
            val textoAlvo = etAlvo.text.toString()

            if (textoAlvo.isNotEmpty()) {
                val valorAlvo = textoAlvo.toDouble()
                
                precoAlvoAtual = valorAlvo
                precoInicialAlarme = ultimoPrecoConhecido
                alarmeAtivo = true
                
                salvarEstadoAlarme(valorAlvo, precoInicialAlarme, atingido = false)
                exibirStatusAlarmeAtivo(valorAlvo)
                enviarAlvoParaRender(valorAlvo)
            } else {
                Toast.makeText(this, "Digite um valor para o alvo", Toast.LENGTH_SHORT).show()
            }
        }

        runnableAtualizacao = object : Runnable {
            override fun run() {
                buscarPrecoBtcCoinbase()
                handler.postDelayed(this, 10000)
            }
        }
    }

    override fun onResume() {
        super.onResume()
        carregarEstadoAlarme()
        
        val filter = IntentFilter("com.example.btcalarm.ALARM_TRIGGERED")
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            registerReceiver(fcmReceiver, filter, RECEIVER_NOT_EXPORTED)
        } else {
            registerReceiver(fcmReceiver, filter)
        }
        
        runnableAtualizacao?.let { handler.post(it) }
    }

    override fun onPause() {
        super.onPause()
        unregisterReceiver(fcmReceiver)
        runnableAtualizacao?.let { handler.removeCallbacks(it) }
    }

    private fun dispararSomAlarme() {
        try {
            var alarmUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_ALARM)
            if (alarmUri == null) {
                alarmUri = RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION)
            }
            val ringtone = RingtoneManager.getRingtone(applicationContext, alarmUri)
            ringtone.play()
        } catch (e: Exception) {
            e.printStackTrace()
        }
    }

    private fun dispararAlarmeAtingido() {
        alarmeAtivo = false
        salvarEstadoAlarme(precoAlvoAtual, precoInicialAlarme, atingido = true)
        exibirStatusAlvoAtingido(precoAlvoAtual)
        dispararSomAlarme()
    }

    private fun buscarPrecoBtcCoinbase() {
        thread {
            try {
                val url = URL("https://api.coinbase.com/v2/prices/BTC-USD/spot")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "GET"
                conn.setRequestProperty("User-Agent", "Mozilla/5.0")

                if (conn.responseCode == 200) {
                    val reader = BufferedReader(InputStreamReader(conn.inputStream))
                    val response = reader.readText()
                    reader.close()

                    val json = JSONObject(response)
                    val preco = json.getJSONObject("data").getString("amount").toDouble()
                    ultimoPrecoConhecido = preco

                    runOnUiThread {
                        tvPrecoAtual.text = String.format("BTC Atual: USD %.2f", preco)

                        if (alarmeAtivo && precoAlvoAtual > 0.0 && precoInicialAlarme > 0.0) {
                            val atingiuAlta = (precoAlvoAtual >= precoInicialAlarme) && (preco >= precoAlvoAtual)
                            val atingiuBaixa = (precoAlvoAtual < precoInicialAlarme) && (preco <= precoAlvoAtual)

                            if (atingiuAlta || atingiuBaixa) {
                                dispararAlarmeAtingido()
                            }
                        }
                    }
                }
                conn.disconnect()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    private fun salvarEstadoAlarme(valorAlvo: Double, precoInicial: Double, atingido: Boolean) {
        val prefs = getSharedPreferences("BtcAlarmPrefs", Context.MODE_PRIVATE)
        prefs.edit()
            .putFloat("target_price", valorAlvo.toFloat())
            .putFloat("initial_price", precoInicial.toFloat())
            .putBoolean("is_triggered", atingido)
            .apply()
    }

    private fun carregarEstadoAlarme() {
        val prefs = getSharedPreferences("BtcAlarmPrefs", Context.MODE_PRIVATE)
        val valorSalvo = prefs.getFloat("target_price", 0f).toDouble()
        val precoInicial = prefs.getFloat("initial_price", 0f).toDouble()
        val atingido = prefs.getBoolean("is_triggered", false)

        if (valorSalvo > 0.0) {
            precoAlvoAtual = valorSalvo
            precoInicialAlarme = precoInicial
            
            if (atingido) {
                alarmeAtivo = false
                exibirStatusAlvoAtingido(valorSalvo)
            } else {
                alarmeAtivo = true
                exibirStatusAlarmeAtivo(valorSalvo)
            }
        } else {
            alarmeAtivo = false
            tvStatusAlarme.text = "Nenhum alarme ativo"
            tvStatusAlarme.setBackgroundColor(Color.parseColor("#E0F7FA"))
            tvStatusAlarme.setTextColor(Color.parseColor("#006064"))
        }
    }

    private fun exibirStatusAlarmeAtivo(valorAlvo: Double) {
        tvStatusAlarme.text = String.format("🚨 Alarme Ativo: USD %.2f", valorAlvo)
        tvStatusAlarme.setBackgroundColor(Color.parseColor("#FFF3E0"))
        tvStatusAlarme.setTextColor(Color.parseColor("#E65100"))
    }

    private fun exibirStatusAlvoAtingido(valorAlvo: Double) {
        tvStatusAlarme.text = String.format("🎯 ALVO ATINGIDO! (USD %.2f)", valorAlvo)
        tvStatusAlarme.setBackgroundColor(Color.parseColor("#FFEBEE"))
        tvStatusAlarme.setTextColor(Color.parseColor("#C62828"))
    }

    private fun obterERegistrarTokenFcm() {
        FirebaseMessaging.getInstance().token.addOnCompleteListener { task ->
            if (task.isSuccessful && task.result != null) {
                enviarTokenParaRender(task.result)
            }
        }
    }

    private fun enviarTokenParaRender(token: String) {
        thread {
            try {
                val url = URL("https://btc-alarm-api.onrender.com/register-token")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json; utf-8")
                conn.doOutput = true

                val jsonPayload = """{"token": "$token"}"""

                OutputStreamWriter(conn.outputStream, "UTF-8").use { os ->
                    os.write(jsonPayload)
                    os.flush()
                }
                conn.responseCode
                conn.disconnect()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }

    private fun enviarAlvoParaRender(valorAlvo: Double) {
        thread {
            try {
                val url = URL("https://btc-alarm-api.onrender.com/set-alarm")
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json; utf-8")
                conn.doOutput = true

                val jsonPayload = """
                    {
                        "target_price": $valorAlvo,
                        "active": true
                    }
                """.trimIndent()

                OutputStreamWriter(conn.outputStream, "UTF-8").use { os ->
                    os.write(jsonPayload)
                    os.flush()
                }

                val responseCode = conn.responseCode
                runOnUiThread {
                    if (responseCode in 200..299) {
                        Toast.makeText(this, "Alvo enviado ao servidor!", Toast.LENGTH_SHORT).show()
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
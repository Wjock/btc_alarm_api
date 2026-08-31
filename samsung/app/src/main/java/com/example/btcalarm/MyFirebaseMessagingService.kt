package com.example.btcalarm

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.os.Build
import android.util.Log
import androidx.core.app.NotificationCompat
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.POST
import retrofit2.Call
import retrofit2.Callback
import retrofit2.Response

interface BtcAlarmApi {
    @POST("register-token")
    fun registrarToken(@Body body: TokenRequest): Call<Void>
}
data class TokenRequest(val token: String)

class MyFirebaseMessagingService : FirebaseMessagingService() {

    override fun onNewToken(token: String) {
        super.onNewToken(token)
        Log.d("FCM_TOKEN", "Token gerado: $token")
        enviarTokenParaAPI(token)
    }

    override fun onMessageReceived(remoteMessage: RemoteMessage) {
        super.onMessageReceived(remoteMessage)
        val titulo = remoteMessage.notification?.title ?: "🚨 ALERTA BITCOIN! 🚨"
        val corpo = remoteMessage.notification?.body ?: "O preço atingiu sua meta!"
        mostrarNotificacao(titulo, corpo)
    }

    private fun enviarTokenParaAPI(token: String) {
        val retrofit = Retrofit.Builder()
            .baseUrl("https://btc-alarm-api.onrender.com")
            .addConverterFactory(GsonConverterFactory.create())
            .build()

        val api = retrofit.create(BtcAlarmApi::class.java)
        
        api.registrarToken(TokenRequest(token)).enqueue(object : Callback<Void> {
            override fun onResponse(call: Call<Void>, response: Response<Void>) {
                if (response.isSuccessful) {
                    Log.d("API_POST", "Token registrado com sucesso no Render!")
                }
            }
            override fun onFailure(call: Call<Void>, t: Throwable) {
                Log.e("API_POST", "Erro de rede ao enviar token: ${t.message}")
            }
        })
    }

    private fun mostrarNotificacao(title: String, body: String) {
        val channelId = "btc_alarm_channel"
        val notificationManager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(channelId, "Alertas BTC", NotificationManager.IMPORTANCE_HIGH)
            notificationManager.createNotificationChannel(channel)
        }

        val builder = NotificationCompat.Builder(this, channelId)
            .setSmallIcon(android.R.drawable.ic_dialog_alert)
            .setContentTitle(title)
            .setContentText(body)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .setAutoCancel(true)

        notificationManager.notify(100, builder.build())
    }
}

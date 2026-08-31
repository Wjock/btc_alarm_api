package btc.alarm

import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.TextView
import androidx.appcompat.app.AppCompatActivity

class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        
        val layout = android.widget.LinearLayout(this).apply {
            orientation = android.widget.LinearLayout.VERTICAL
            setPadding(50, 50, 50, 50)
        }

        val titulo = TextView(this).apply {
            text = "Alarme de Bitcoin"
            textSize = 24f
            setPadding(0, 0, 0, 30)
        }

        val inputAlvo = EditText(this).apply {
            hint = "Digite o valor alvo em USD (ex: 60000)"
            inputType = android.text.InputType.TYPE_CLASS_NUMBER
        }

        val btnSalvar = Button(this).apply {
            text = "Ativar Alarme"
            setOnClickListener {
                val valor = inputAlvo.text.toString()
                titulo.text = "Alarme definido para: $$valor"
            }
        }

        layout.addView(titulo)
        layout.addView(inputAlvo)
        layout.addView(btnSalvar)

        setContentView(layout)
    }
}

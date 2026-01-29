<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Red Deploy</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
        }
        
        body {
            background-color: #0a0e17;
            color: #e2e8f0;
            line-height: 1.6;
            padding: 20px;
            min-height: 100vh;
        }
        
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            padding-bottom: 15px;
            border-bottom: 1px solid #2d3748;
        }
        
        .logo {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .logo i {
            color: #ff4757;
            font-size: 24px;
        }
        
        .logo h1 {
            font-size: 28px;
            font-weight: 700;
            background: linear-gradient(90deg, #ff4757, #ff6b81);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .weather {
            display: flex;
            align-items: center;
            gap: 8px;
            background: rgba(255, 71, 87, 0.1);
            padding: 8px 15px;
            border-radius: 20px;
            border: 1px solid #ff4757;
        }
        
        .weather i {
            color: #ffd700;
        }
        
        .main-content {
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: 30px;
        }
        
        .sidebar {
            background: #1a202c;
            border-radius: 12px;
            padding: 25px;
            border: 1px solid #2d3748;
        }
        
        .section-title {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 20px;
            color: #ff6b81;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .section-title i {
            font-size: 16px;
        }
        
        .architecture-list {
            list-style: none;
            margin-bottom: 30px;
        }
        
        .architecture-list li {
            padding: 12px 0;
            border-bottom: 1px solid #2d3748;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .architecture-list li:last-child {
            border-bottom: none;
        }
        
        .badge {
            background: linear-gradient(90deg, #ff4757, #ff6b81);
            color: white;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 600;
        }
        
        hr {
            border: none;
            height: 1px;
            background-color: #2d3748;
            margin: 25px 0;
        }
        
        .chat-preview {
            background: rgba(255, 107, 129, 0.05);
            border-radius: 10px;
            padding: 15px;
            border: 1px solid #2d3748;
            margin-top: 20px;
        }
        
        .chat-header {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
            font-size: 14px;
            color: #a0aec0;
        }
        
        .chat-message {
            color: #e2e8f0;
            font-size: 15px;
        }
        
        .deployments {
            background: #1a202c;
            border-radius: 12px;
            padding: 25px;
            border: 1px solid #2d3748;
        }
        
        .deployment-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 25px;
        }
        
        .status-badge {
            padding: 6px 15px;
            border-radius: 20px;
            font-weight: 600;
            font-size: 14px;
        }
        
        .active {
            background-color: rgba(72, 187, 120, 0.2);
            color: #48bb78;
            border: 1px solid #48bb78;
        }
        
        .failed {
            background-color: rgba(245, 101, 101, 0.2);
            color: #f56565;
            border: 1px solid #f56565;
        }
        
        .deployment-card {
            background: #0a0e17;
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 25px;
            border: 1px solid #2d3748;
        }
        
        .deployment-time {
            color: #a0aec0;
            font-size: 14px;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }
        
        .deployment-time i {
            color: #ff6b81;
        }
        
        .deployment-status {
            font-weight: 600;
            margin: 15px 0;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        
        .success {
            color: #48bb78;
        }
        
        .failure {
            color: #f56565;
        }
        
        .btn {
            background: transparent;
            color: #ff6b81;
            border: 1px solid #ff6b81;
            padding: 8px 20px;
            border-radius: 6px;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.3s;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            text-decoration: none;
        }
        
        .btn:hover {
            background: rgba(255, 107, 129, 0.1);
        }
        
        .build-steps {
            margin-top: 20px;
            padding-left: 20px;
        }
        
        .build-step {
            margin-bottom: 15px;
            position: relative;
            padding-left: 30px;
        }
        
        .build-step:before {
            content: '';
            position: absolute;
            left: 0;
            top: 8px;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            background-color: #2d3748;
        }
        
        .build-step.failed:before {
            background-color: #f56565;
        }
        
        .build-step.success:before {
            background-color: #48bb78;
        }
        
        .build-step.neutral:before {
            background-color: #a0aec0;
        }
        
        .step-time {
            color: #a0aec0;
            font-size: 13px;
            margin-left: 10px;
        }
        
        .error-details {
            background: rgba(245, 101, 101, 0.1);
            border-left: 3px solid #f56565;
            padding: 15px;
            margin-top: 15px;
            border-radius: 0 6px 6px 0;
            font-size: 14px;
        }
        
        .error-details i {
            color: #f56565;
            margin-right: 8px;
        }
        
        footer {
            margin-top: 40px;
            text-align: center;
            color: #a0aec0;
            font-size: 14px;
            padding-top: 20px;
            border-top: 1px solid #2d3748;
        }
        
        @media (max-width: 968px) {
            .main-content {
                grid-template-columns: 1fr;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="logo">
                <i class="fas fa-fire"></i>
                <h1>Red deploy</h1>
            </div>
            <div class="weather">
                <i class="fas fa-cloud"></i>
                <span>4°C Mostly cloudy</span>
            </div>
        </header>
        
        <div class="main-content">
            <div class="sidebar">
                <div class="section-title">
                    <i class="fas fa-sitemap"></i>
                    <span>Architecture</span>
                </div>
                <ul class="architecture-list">
                    <li>Observability</li>
                    <li>Logs</li>
                    <li>Settings</li>
                    <li>
                        <span>30 days left</span>
                        <span class="badge">$4.99</span>
                    </li>
                </ul>
                
                <hr>
                
                <div class="chat-preview">
                    <div class="chat-header">
                        <span>TDTru Studentlari → Shokhr...</span>
                        <span>12:45 PM</span>
                    </div>
                    <div class="chat-message">
                        Allayor: Assalomu alaykum Qadri baland qadrdonlarim Sizga ...
                    </div>
                </div>
            </div>
            
            <div class="deployments">
                <div class="deployment-header">
                    <h2 class="section-title">Deployments</h2>
                </div>
                
                <div class="deployment-card">
                    <div class="deployment-time">
                        <i class="fab fa-github"></i>
                        <span>5 hours ago via GitHub</span>
                        <span class="status-badge active">ACTIVE</span>
                    </div>
                    
                    <div class="deployment-status success">
                        <i class="fas fa-check-circle"></i>
                        <span>Deployment successful</span>
                    </div>
                    
                    <a href="#" class="btn">
                        <i class="fas fa-file-alt"></i>
                        View logs
                    </a>
                </div>
                
                <h2 class="section-title" style="margin-top: 40px;">History</h2>
                
                <div class="deployment-card">
                    <div class="deployment-time">
                        <i class="fab fa-github"></i>
                        <span>Update requirements.txt</span>
                        <span class="status-badge failed">FAILED</span>
                    </div>
                    <div class="deployment-time">
                        <i class="far fa-clock"></i>
                        <span>1 minute ago via GitHub</span>
                    </div>
                    
                    <div class="deployment-status failure">
                        <i class="fas fa-exclamation-circle"></i>
                        <span>Deployment failed during build process</span>
                        <span class="step-time">(00:24)</span>
                    </div>
                    
                    <div class="build-steps">
                        <div class="build-step neutral">
                            Initialization
                            <span class="step-time">(00:00)</span>
                        </div>
                        <div class="build-step failed">
                            Build > Build image
                            <span class="step-time">(00:05)</span>
                        </div>
                    </div>
                    
                    <div class="error-details">
                        <i class="fas fa-exclamation-triangle"></i>
                        Failed to build an image. Please check the build logs for more details.
                        <br>
                        Install site packages: python secret ADMIN_ID not found
                    </div>
                    
                    <a href="#" class="btn" style="margin-top: 20px;">
                        <i class="fas fa-file-alt"></i>
                        View logs
                    </a>
                </div>
            </div>
        </div>
        
        <footer>
            <p>Red Deploy Dashboard • v2.1.4 • © 2023 All rights reserved</p>
        </footer>
    </div>

    <script>
        // Add interactivity for buttons
        document.querySelectorAll('.btn').forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                const deploymentType = this.closest('.deployment-card').querySelector('.status-badge').textContent;
                alert(`Viewing logs for ${deploymentType} deployment...`);
            });
        });
        
        // Simulate real-time update for the failed deployment time
        function updateTime() {
            const timeElement = document.querySelector('.deployment-time:nth-child(2) span:nth-child(2)');
            const now = new Date();
            const minutesAgo = Math.floor(Math.random() * 5) + 1;
            timeElement.textContent = `${minutesAgo} minute${minutesAgo > 1 ? 's' : ''} ago via GitHub`;
        }
        
        // Update time every minute
        setInterval(updateTime, 60000);
        
        // Weather update simulation
        const weatherElement = document.querySelector('.weather span');
        const weatherConditions = ['Mostly cloudy', 'Partly sunny', 'Light rain', 'Clear'];
        const temperatures = [3, 4, 5, 6, 7];
        
        function updateWeather() {
            const randomTemp = temperatures[Math.floor(Math.random() * temperatures.length)];
            const randomCondition = weatherConditions[Math.floor(Math.random() * weatherConditions.length)];
            weatherElement.textContent = `${randomTemp}°C ${randomCondition}`;
        }
        
        // Update weather every 5 minutes
        setInterval(updateWeather, 300000);
    </script>
</body>
</html>
